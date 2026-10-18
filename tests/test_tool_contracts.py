import asyncio
from email import policy
from email.parser import BytesParser
from pathlib import Path

from loguru import logger
from mcp_types import CallToolRequestParams
import pytest

from app.config import IMAPConfig
from app.imap import ICloudIMAPService
from app.mcp_server import create_mcp_server
from app.tool_reference import reference
from test_imap import FakeIMAP, service_with


def invoke(server, name, **arguments):
    return asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments)))


def test_catalogue_describes_every_parameter_and_nested_input_field():
    tools = asyncio.run(create_mcp_server(None).list_tools())
    for tool in tools:
        assert "Workflow:" in tool.description
        assert "Result interpretation:" in tool.description
        assert "Failures and recovery:" in tool.description
        assert tool.input_schema["additionalProperties"] is False
        for name, field in tool.input_schema.get("properties", {}).items():
            assert field["description"]
            assert f"- {name}:" in tool.description
        for definition in tool.input_schema.get("$defs", {}).values():
            assert definition["additionalProperties"] is False
            for field in definition.get("properties", {}).values():
                assert field["description"]
    drafts = [tool for tool in tools if tool.name in {"create_draft", "update_draft"}]
    for draft in drafts:
        assert draft.input_schema["properties"]["body_format"]["enum"] == ["plain", "html"]
        attachment = draft.input_schema["$defs"]["DraftAttachment"]
        assert set(attachment["required"]) == {"filename", "content_base64"}
        assert attachment["properties"]["content_type"]["default"] == "application/octet-stream"
        assert "not format" in draft.description


@pytest.mark.parametrize("extra", [
    {"body_format": "text"},
    {"format": "plain"},
    {"from_name": "PRIVATE_INPUT_MARKER"},
    {"attachments": [{"filename": "note.txt"}]},
    {"attachments": [{"filename": "note.txt", "content_base64": "YQ==", "path": "PRIVATE_INPUT_MARKER"}]},
    {"to": "PRIVATE_INPUT_MARKER"},
])
def test_invalid_draft_contract_does_not_write_or_log_input(extra):
    class Mail:
        calls = 0

        def create_draft(self, **arguments):
            self.calls += 1
            raise AssertionError("Validation must run before service access")

    mail = Mail()
    server = create_mcp_server(None, imap_service=mail)
    logs = []
    sink = logger.add(lambda message: logs.append(str(message)))
    try:
        result = invoke(server, "create_draft", **{
            "to": ["person@example.com"], "subject": "PRIVATE_INPUT_MARKER",
            "body": "PRIVATE_INPUT_MARKER", **extra,
        })
    finally:
        logger.remove(sink)
    assert result.is_error is True
    assert mail.calls == 0
    assert "PRIVATE_INPUT_MARKER" not in str(result)
    assert "PRIVATE_INPUT_MARKER" not in "".join(logs)
    assert "no remote request was made" in str(result)
    if extra.get("body_format") == "text":
        assert "plain" in str(result) and "html" in str(result)


def test_draft_attachment_contract_reaches_mime_builder_with_defaults():
    client = FakeIMAP()
    result = invoke(create_mcp_server(None, imap_service=service_with(client)), "create_draft",
                    to=["person@example.com"], subject="Example", body="Example", body_format="html",
                    attachments=[{"filename": "note.txt", "content_base64": "YQ=="}])
    assert result.is_error is False
    append = next(arguments for command, arguments in client.calls if command == "APPEND")
    message = BytesParser(policy=policy.default).parsebytes(append[3])
    assert message.get_body(preferencelist=("html",)).get_content_type() == "text/html"
    attachment = next(message.iter_attachments())
    assert attachment.get_payload(decode=True) == b"a"
    assert attachment.get_content_type() == "application/octet-stream"


@pytest.mark.parametrize("from_header, expected_name", [(None, ""), ("Example Author <author@example.com>", "Example Author")])
def test_draft_result_reports_submitted_header_without_inferring_signature(from_header, expected_name):
    client = FakeIMAP()
    result = service_with(client).create_draft(
        to=["person@example.com"], subject="Example", body="Regards, Someone Else", from_address=from_header,
    )
    append = next(arguments for command, arguments in client.calls if command == "APPEND")
    message = BytesParser(policy=policy.default).parsebytes(append[3])
    assert result["from_header"] == str(message["From"])
    assert result["from_name"] == expected_name
    assert result["from_address"] == ("author@example.com" if from_header else "user@example.com")
    assert result["sent"] is False
    assert result["send_as_permissions_verified"] is False


def test_account_info_is_configuration_only_and_does_not_guess_provider():
    client = FakeIMAP()
    config = IMAPConfig(username="account@example.com", app_specific_password="PRIVATE_PASSWORD",
                        host="mirror.example.com", drafts_mailbox="[Gmail]/Drafts")
    service = ICloudIMAPService(config, client_factory=lambda **_: client)
    result = invoke(create_mcp_server(None, imap_service=service), "mail_account_info")
    assert result.is_error is False
    assert client.calls == []
    assert result.structured_content["host"] == "mirror.example.com"
    assert result.structured_content["configured_drafts_mailbox"] == "[Gmail]/Drafts"
    assert result.structured_content["upstream_provider_verified"] is False
    assert "PRIVATE_PASSWORD" not in str(result)


def test_failed_draft_timeout_gives_safe_category_without_retrying():
    class Mail:
        calls = 0

        def create_draft(self, **arguments):
            self.calls += 1
            raise TimeoutError("PRIVATE_UPSTREAM_MARKER")

    mail = Mail()
    result = invoke(create_mcp_server(None, imap_service=mail), "create_draft",
                    to=["person@example.com"], subject="Example", body="Example")
    assert result.is_error is True
    assert mail.calls == 1
    assert result.structured_content["error"]["code"] == "timeout"
    assert result.structured_content["error"]["write_status"] == "unknown"
    assert result.structured_content["error"]["inspect_before_retry"] is True
    assert "PRIVATE_UPSTREAM_MARKER" not in str(result)


def test_checked_in_reference_matches_published_contracts():
    assert Path("docs/mcp-tools.md").read_text(encoding="utf-8") == asyncio.run(reference())
