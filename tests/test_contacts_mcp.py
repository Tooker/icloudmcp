import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
from loguru import logger
from mcp_types import CallToolRequestParams
import pytest
from pydantic import ValidationError

from app.config import ContactsConfig, load_contacts_config
from app.contacts import ICloudContactsService
from app.contacts_schemas import ContactInput
from app.main import create_app
from app.mcp_server import create_mcp_server
from test_contacts import CardDAV


def call(server, name, **arguments):
    return asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name=name, arguments=arguments)))


def test_contact_tool_schemas_and_annotations():
    tools = {tool.name: tool for tool in asyncio.run(create_mcp_server(None).list_tools())}
    for name in ("list_addressbooks", "list_contacts", "search_contacts", "get_contact"):
        assert tools[name].annotations.read_only_hint is True
        assert tools[name].annotations.idempotent_hint is True
    create = tools["create_contact"]
    assert create.annotations.read_only_hint is False
    assert create.annotations.destructive_hint is False
    assert create.annotations.idempotent_hint is False
    assert create.input_schema["required"] == ["contact"]
    assert "ContactInput" in create.input_schema["$defs"]


def test_mcp_contacts_not_configured_is_safe_and_explicit():
    server = create_mcp_server(None)
    result = call(server, "list_contacts")
    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "not_configured"
    result = call(server, "create_contact", contact={"given_name": "New"})
    assert result.is_error is True
    assert result.structured_content["write_status"] == "not_sent"


def test_mcp_creation_converts_structured_input_and_keeps_uncertainty():
    dav = CardDAV()
    contacts = ICloudContactsService(ContactsConfig("user", "password"), transport=httpx.MockTransport(dav))
    server = create_mcp_server(None, contacts_service=contacts)
    result = call(server, "create_contact", contact={"given_name": "New", "emails": [{"value": "new@example.invalid", "label": "home"}]})
    assert result.is_error is False
    assert result.structured_content["write_status"] == "succeeded"
    dav.put_exception = httpx.ReadTimeout("PRIVATE_UPSTREAM")
    result = call(server, "create_contact", contact={"given_name": "Another"})
    assert result.is_error is True
    assert result.structured_content["write_status"] == "unknown"
    assert result.structured_content["contact_id"]
    assert "PRIVATE_UPSTREAM" not in str(result)


def test_mcp_logs_only_safe_counts_and_timings():
    dav = CardDAV()
    contacts = ICloudContactsService(ContactsConfig("user", "password"), transport=httpx.MockTransport(dav))
    logs = []
    sink = logger.add(lambda message: logs.append(str(message)))
    try:
        server = create_mcp_server(None, contacts_service=contacts)
        result = call(server, "search_contacts", query="Änne")
        assert result.is_error is False
        result = call(server, "create_contact", contact={"given_name": "PRIVATE_NAME"})
        assert result.is_error is False
    finally:
        logger.remove(sink)
    text = "".join(logs)
    assert "mcp_tool_start tool=search_contacts" in text
    assert "mcp_tool_complete tool=create_contact" in text
    assert "mcp_phase" in text and "parent_span=" in text
    for marker in ("Änne", "PRIVATE_NAME", "native-contact-uid", "contacts.icloud.com", "existing.vcf", result.structured_content["contact_id"]):
        assert marker not in text


@pytest.mark.parametrize("contact", [
    {}, {"emails": [{"value": "only@example.invalid"}]}, {"given_name": " "},
    {"given_name": "New", "birthday": "2025-02-29"}, {"given_name": "New", "birthday": "--02-29"},
    {"given_name": "New\r\nUID:injection"}, {"given_name": "New", "unknown_field": "unsupported"},
    {"given_name": "New", "addresses": [{"label": "home"}]},
])
def test_invalid_contact_input_is_rejected_before_any_request(contact):
    with pytest.raises(ValidationError):
        ContactInput.model_validate(contact)
    dav = CardDAV()
    server = create_mcp_server(None, contacts_service=ICloudContactsService(ContactsConfig("user", "password"), transport=httpx.MockTransport(dav)))
    assert call(server, "create_contact", contact=contact).is_error is True
    assert dav.requests == []


def test_contacts_can_run_independently_without_startup_network_access(tmp_path: Path):
    app = create_app(tmp_path / "missing.yaml", environ={"CARDDAV_USERNAME": "user", "CARDDAV_APP_PASSWORD": "password"})
    assert app.state.icloud_service is None
    assert app.state.imap_service is None
    assert app.state.contacts_service is not None
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/contacts").status_code == 404


def test_contacts_config_defaults_shared_fallback_and_secret_repr(tmp_path: Path):
    path = tmp_path / "missing.yaml"
    assert load_contacts_config(path, {}) is None
    config = load_contacts_config(path, {"ICLOUD_USERNAME": "private-user", "ICLOUD_APP_PASSWORD": "private-password"})
    assert config.username == "private-user"
    assert config.carddav_url == "https://contacts.icloud.com/"
    assert config.timeout_seconds == 60
    assert config.max_contacts == 5000
    assert "private-user" not in repr(config) and "private-password" not in repr(config)


def test_contacts_config_yaml_and_dedicated_env_precedence(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("icloud:\n  username: shared\n  app_specific_password: shared-secret\ncontacts:\n  username: yaml\n  app_specific_password: yaml-secret\n  default_addressbook: ab_example\n  timeout_seconds: 30\n  max_contacts: 250\n")
    config = load_contacts_config(path, {"CARDDAV_USERNAME": "env", "CARDDAV_APP_PASSWORD": "env-secret"})
    assert config.username == "env" and config.app_specific_password == "env-secret"
    assert config.default_addressbook == "ab_example"
    assert config.timeout_seconds == 30 and config.max_contacts == 250


@pytest.mark.parametrize("settings", [
    {"CARDDAV_USERNAME": "only"}, {"CARDDAV_APP_PASSWORD": "only"},
    {"CARDDAV_URL": "http://contacts.icloud.com/"}, {"CARDDAV_URL": "https://user:password@contacts.icloud.com/"},
    {"CARDDAV_URL": "https://contacts.icloud.com:invalid/"}, {"CARDDAV_URL": "https://contacts.icloud.com/?secret=value"},
    {"CARDDAV_TIMEOUT_SECONDS": "0"}, {"CARDDAV_TIMEOUT_SECONDS": "301"},
    {"CARDDAV_MAX_CONTACTS": "20001"}, {"CARDDAV_MAX_CONTACTS": "x"},
])
def test_invalid_contacts_config_is_safe(tmp_path: Path, settings):
    env = settings if len(settings) == 1 and next(iter(settings)) in ("CARDDAV_USERNAME", "CARDDAV_APP_PASSWORD") else {"ICLOUD_USERNAME": "user", "ICLOUD_APP_PASSWORD": "secret", **settings}
    with pytest.raises(ValueError) as error:
        load_contacts_config(tmp_path / "missing.yaml", env)
    assert "secret=value" not in str(error.value)


@pytest.mark.parametrize("value", ["[]", "false", "1", "not-an-object"])
def test_contacts_yaml_requires_an_object(tmp_path: Path, value):
    path = tmp_path / "config.yaml"
    path.write_text("contacts: " + value + "\n")
    with pytest.raises(ValueError, match="must be objects"):
        load_contacts_config(path, {})
