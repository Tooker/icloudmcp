import json
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest
from mcp_types import CallToolRequestParams
import asyncio
import threading

from fastapi.testclient import TestClient
from app.main import create_app

from app.icloud_cache import SQLiteICloudCalendarCache
from app.mcp_server import create_mcp_server
from app.search_clients import MailSearchError, OpenAIEmbeddings, QdrantMailIndex
from app.search_config import MailSearchConfig, load_mail_search_config
from app.search_documents import html_text, text_chunks
from app.semantic_search import SemanticMailSearch


class FakeEmbeddings:
    def __init__(self):
        self.calls = []
        self.on_embed = lambda: None
        self.closed = False

    def embed(self, texts):
        self.calls.append(texts)
        self.on_embed()
        return [[1.0, 0.0, 0.0] for _ in texts]

    def close(self):
        self.closed = True


class FakeIndex:
    def __init__(self):
        self.points = {}
        self.fail = False
        self.closed = False

    def ensure_collection(self):
        return False, len(self.points)

    def delete_document(self, key):
        self.points = {id: point for id, point in self.points.items() if point["payload"]["document_key"] != key}

    def replace_document(self, key, points):
        self.delete_document(key)
        if self.fail:
            self.fail = False
            self.points.update({point["id"]: point for point in points[:1]})
            raise MailSearchError("Qdrant is unavailable.")
        self.points.update({point["id"]: point for point in points})

    def search(self, vector, *, mailbox, source, limit):
        return [{**point, "score": 1.0} for point in self.points.values()
                if (mailbox is None or point["payload"]["mailbox"] == mailbox)
                and (source is None or point["payload"]["source"] == source)][:limit]

    def close(self):
        self.closed = True


def cache_and_mail(tmp_path: Path, username="alice@example.com"):
    now = [100.0]
    cache = SQLiteICloudCalendarCache(tmp_path / "cache.sqlite3", clock=lambda: now[0]).for_account("imap", "mail.example.com:993", username)
    cache.sync_uid_validity("INBOX", "7")
    put_mail(cache)
    return cache, now


def put_mail(cache, uid="42", text="Die Heizkostenabrechnung ist bezahlt.", generation="7", pdf=None):
    message = EmailMessage()
    message["Subject"] = "Abrechnung"
    message["From"] = "sender@example.com"
    message.set_content(text)
    if pdf is not None:
        message.add_attachment(pdf, maintype="application", subtype="pdf", filename="rechnung.pdf")
    cache.set_email_messages([{
        "mailbox": "INBOX", "uid": uid, "uid_validity": generation,
        "raw_message": message.as_bytes(), "summary": {"uid": uid, "subject": "Abrechnung", "flags": []},
    }])


def search_service(cache, *, embeddings=None, index=None, config=None):
    embeddings = embeddings if embeddings is not None else FakeEmbeddings()
    index = index if index is not None else FakeIndex()
    config = config or MailSearchConfig(enabled=True, dimensions=3, embedding_mode="standard")
    return SemanticMailSearch(cache, config, embeddings=embeddings, index=index), embeddings, index


def test_pdf_hit_contains_original_mail_and_attachment_references(tmp_path):
    from test_imap import pdf_attachment

    cache, _ = cache_and_mail(tmp_path)
    put_mail(cache, pdf=pdf_attachment("Rechnungsnummer 2026-123 Betrag 42 EUR"))
    search, embeddings, index = search_service(cache)
    search.run_once()
    result = search.search("Rechnung 42 Euro", source="attachment")
    hit = result["matches"][0]
    assert "42 EUR" in hit["excerpt"]
    assert hit["filename"] == "rechnung.pdf"
    assert hit["email"] == {"tool": "get_email", "arguments": {"uid": "42", "mailbox": "INBOX", "expected_uid_validity": "7"}}
    assert hit["attachment"]["arguments"]["attachment_id"] == "1"
    assert result["index"]["indexed_messages"] == 1
    assert result["index"]["pending_messages"] == 0
    assert "document_key" not in hit
    assert "embedding_text" not in hit


def test_restart_refresh_and_lost_qdrant_do_not_reembed_unchanged_text(tmp_path):
    cache, now = cache_and_mail(tmp_path)
    first, embeddings, index = search_service(cache)
    first.run_once()
    assert len(embeddings.calls) == 1
    now[0] += 10
    put_mail(cache)
    second, _, _ = search_service(cache, embeddings=embeddings, index=index)
    second.run_once()
    assert len(embeddings.calls) == 1
    assert second.status()["pending_messages"] == 0
    third, _, rebuilt = search_service(cache, embeddings=embeddings, index=FakeIndex())
    third.run_once()
    assert rebuilt.points
    assert len(embeddings.calls) == 1


def test_uid_generation_and_deletion_hide_old_results_before_cleanup(tmp_path):
    cache, now = cache_and_mail(tmp_path)
    search, _, index = search_service(cache)
    search.run_once()
    old_ids = set(index.points)
    cache.sync_uid_validity("INBOX", "99")
    assert search.search("Abrechnung")["matches"] == []
    now[0] += 10
    put_mail(cache, text="Eine ganz andere Nachricht.", generation="99")
    search.run_once()
    assert old_ids.isdisjoint(index.points)
    assert search.search("andere")["matches"][0]["uid_validity"] == "99"
    cache.invalidate_email_messages("INBOX")
    assert search.search("andere")["matches"] == []
    search.run_once()
    assert not index.points


def test_source_invalidated_during_embedding_is_not_published(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    search, embeddings, index = search_service(cache)
    embeddings.on_embed = lambda: cache.sync_uid_validity("INBOX", "99")
    search.run_once()
    assert not index.points
    assert search.status()["indexed_messages"] == 0


def test_partial_qdrant_write_retries_from_persisted_vectors(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    search, embeddings, index = search_service(cache)
    index.fail = True
    with pytest.raises(MailSearchError):
        search.run_once()
    assert search.status()["indexed_messages"] == 0
    restarted, _, _ = search_service(cache, embeddings=embeddings, index=index)
    restarted.run_once()
    assert restarted.status()["indexed_messages"] == 1
    assert len(embeddings.calls) == 1


def test_accounts_are_isolated_even_with_same_mailbox_and_uid(tmp_path):
    alice, _ = cache_and_mail(tmp_path)
    bob, _ = cache_and_mail(tmp_path, "bob@example.com")
    put_mail(bob, text="Private Nachricht von Bob")
    first, _, shared_index = search_service(alice)
    first.run_once()
    second, _, _ = search_service(bob, index=shared_index)
    assert second.store.pending(100)
    assert second.collection != first.collection
    second.run_once()
    hits = second.search("Nachricht")["matches"]
    assert len(hits) == 1
    assert "Bob" in hits[0]["excerpt"]


def test_unicode_chunks_are_bounded_and_html_does_not_include_scripts():
    content = "Grüße aus Köln 🥨 " * 3000
    chunks = list(text_chunks(content, "Titel"))
    assert len(chunks) > 1
    assert all(len(embedding_text.encode("utf-8")) <= 6500 for embedding_text, _ in chunks)
    assert all("�" not in excerpt for _, excerpt in chunks)
    assert html_text("<style>hidden</style><p>Hallo &amp; Grüße</p><script>private</script>") == "Hallo & Grüße"


def test_configuration_defaults_validation_and_secret_repr():
    config = load_mail_search_config({"OPENAI_API_KEY": "PRIVATE_KEY", "QDRANT_API_KEY": "OTHER_PRIVATE_KEY"})
    assert config.model == "text-embedding-3-large"
    assert config.dimensions == 3072
    assert config.embedding_mode == "batch"
    assert not config.enabled
    assert "PRIVATE_KEY" not in repr(config)
    assert load_mail_search_config({"OPENAI_EMBEDDING_MODEL": "text-embedding-3-small", "OPENAI_EMBEDDING_DIMENSIONS": ""}).dimensions == 1536
    with pytest.raises(ValueError):
        load_mail_search_config({"OPENAI_EMBEDDING_MODEL": "gpt-5"})
    with pytest.raises(ValueError):
        load_mail_search_config({"OPENAI_EMBEDDING_DIMENSIONS": "4000"})


def test_embedding_errors_do_not_expose_provider_details():
    client = OpenAIEmbeddings(MailSearchConfig(dimensions=3), transport=httpx.MockTransport(
        lambda request: httpx.Response(429, json={"error": {"message": "PRIVATE_INPUT_AND_KEY"}})))
    with pytest.raises(MailSearchError) as error:
        client.embed(["mail text"])
    assert "PRIVATE" not in str(error.value)
    assert error.value.status_code == 429
    client.close()


def test_embedding_vectors_are_reordered_and_validated():
    client = OpenAIEmbeddings(MailSearchConfig(dimensions=3), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0, 1, 0]}, {"index": 0, "embedding": [1, 0, 0]},
        ]})))
    assert client.embed(["one", "two"]) == [[1, 0, 0], [0, 1, 0]]
    with pytest.raises(MailSearchError):
        client.embed(["one"])
    client.close()


def test_qdrant_rest_contract_uses_disk_storage_filters_and_waited_writes():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, dict(request.url.params), json.loads(request.content) if request.content else None))
        if request.method == "GET":
            return httpx.Response(404)
        if request.url.path.endswith("/query"):
            return httpx.Response(200, json={"result": {"points": []}})
        return httpx.Response(200, json={"result": {"status": "completed"}})

    index = QdrantMailIndex(MailSearchConfig(dimensions=3), "test-collection", transport=httpx.MockTransport(handler))
    assert index.ensure_collection() == (True, 0)
    index.replace_document("opaque-key", [{"id": "a", "vector": [1, 0, 0], "payload": {"document_key": "opaque-key"}}])
    assert index.search([1, 0, 0], mailbox="INBOX", source="attachment", limit=10) == []
    assert calls[1][3]["vectors"] == {"size": 3, "distance": "Cosine", "on_disk": True}
    assert calls[2][2]["wait"] == "true"
    assert calls[2][3]["filter"]["must"][0]["match"]["value"] == "opaque-key"
    assert calls[-1][3]["filter"]["must"] == [
        {"key": "mailbox", "match": {"value": "INBOX"}},
        {"key": "source", "match": {"value": "attachment"}},
    ]
    index.close()


class FakeBatchAPI:
    def __init__(self):
        self.uploads = 0
        self.creations = 0
        self.completed = False
        self.timeout_create = False
        self.reject_create = False
        self.partial = False
        self.requests = []
        self.metadata = {}
        self.sync_requests = 0
        self.deleted = set()
        self.output_reads = 0
        self.cleanup_fail = False

    def __call__(self, request):
        path = request.url.path
        if path == "/v1/files" and request.method == "POST":
            self.uploads += 1
            self.requests = [json.loads(line) for line in request.content.splitlines() if line.startswith(b'{"custom_id"')]
            return httpx.Response(200, json={"id": "file-input"})
        if path == "/v1/batches" and request.method == "POST":
            self.creations += 1
            self.metadata = json.loads(request.content)["metadata"]
            if self.reject_create:
                self.reject_create = False
                return httpx.Response(429, json={"error": {"message": "PRIVATE"}})
            if self.timeout_create:
                self.timeout_create = False
                raise httpx.ReadTimeout("PRIVATE_DETAILS", request=request)
            return httpx.Response(200, json={"id": "batch-1", "status": "validating"})
        if path == "/v1/batches" and request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "batch-1", "status": "in_progress", "metadata": self.metadata}], "has_more": False})
        if path == "/v1/batches/batch-1":
            return httpx.Response(200, json={"id": "batch-1", "status": ("expired" if self.partial else "completed") if self.completed else "in_progress", "output_file_id": "file-output" if self.completed else None, "error_file_id": "file-error"})
        if path == "/v1/files/file-output/content":
            if "/v1/files/file-output" in self.deleted:
                return httpx.Response(404)
            self.output_reads += 1
            rows = self.requests[:1] if self.partial else self.requests
            lines = [json.dumps({"custom_id": row["custom_id"], "response": {"status_code": 200, "body": {"data": [{"index": 0, "embedding": [1, 0, 0] if self.requests.index(row) == 0 else [0, 1, 0]}]}}, "error": None}) for row in reversed(rows)]
            return httpx.Response(200, text="\n".join(lines))
        if path.startswith("/v1/files/") and request.method == "DELETE":
            if path.endswith("file-error") and self.cleanup_fail:
                self.cleanup_fail = False
                return httpx.Response(503)
            self.deleted.add(path)
            return httpx.Response(200, json={"deleted": True})
        if path == "/v1/embeddings":
            self.sync_requests += 1
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0, 0]}]})
        raise AssertionError(f"Unexpected API request {request.method} {path}")


def batch_service(cache, api, index=None):
    config = MailSearchConfig(enabled=True, dimensions=3, embedding_mode="batch")
    embeddings = OpenAIEmbeddings(config, transport=httpx.MockTransport(api))
    return search_service(cache, embeddings=embeddings, index=index, config=config)


def test_batch_survives_restart_and_maps_reordered_results_to_sources(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    put_mail(cache, uid="43", text="Eine zweite Nachricht.")
    api = FakeBatchAPI()
    first, _, index = batch_service(cache, api)
    first.run_once()
    assert first.status()["batch"]["inputs"] == 2
    assert api.sync_requests == 0
    assert first.status()["indexed_messages"] == 0
    restarted, _, _ = batch_service(cache, api, index=index)
    restarted.run_once()
    assert api.creations == 1
    api.completed = True
    restarted.run_once()
    assert restarted.status()["indexed_messages"] == 2
    assert restarted.status()["batch"] is None
    assert len(index.points) == 2
    assert len(api.deleted) == 3
    assert restarted.store.get_vector(api.requests[0]["custom_id"], 3) == [1, 0, 0]
    assert restarted.store.get_vector(api.requests[1]["custom_id"], 3) == [0, 1, 0]
    restarted.search("Heizkosten")
    assert api.sync_requests == 1
    restarted.search("Heizkosten")
    assert api.sync_requests == 1


def test_batch_create_timeout_recovers_accepted_job_without_duplicate_charge(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    api = FakeBatchAPI()
    api.timeout_create = True
    first, _, index = batch_service(cache, api)
    with pytest.raises(MailSearchError):
        first.run_once()
    restarted, _, _ = batch_service(cache, api, index=index)
    restarted.run_once()
    assert api.creations == 1
    assert api.uploads == 1
    assert restarted.status()["batch"]["id"] == "batch-1"


def test_rejected_batch_can_retry_without_reuploading_input(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    api = FakeBatchAPI()
    api.reject_create = True
    search, _, _ = batch_service(cache, api)
    with pytest.raises(MailSearchError):
        search.run_once()
    search.run_once()
    assert api.creations == 2
    assert api.uploads == 1


def test_partial_expired_batch_retains_successes_and_retries_only_missing(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    put_mail(cache, uid="43", text="Andere Mail.")
    api = FakeBatchAPI()
    search, _, _ = batch_service(cache, api)
    search.run_once()
    successful = api.requests[0]["custom_id"]
    api.completed = True
    api.partial = True
    with pytest.raises(MailSearchError):
        search.run_once()
    assert search.store.get_vector(successful, 3) is not None
    api.completed = False
    api.partial = False
    search.run_once()
    assert len(api.requests) == 1
    assert api.requests[0]["custom_id"] != successful


def test_batch_file_cleanup_survives_restart_after_output_was_deleted(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    api = FakeBatchAPI()
    first, _, index = batch_service(cache, api)
    first.run_once()
    api.completed = True
    api.cleanup_fail = True
    with pytest.raises(MailSearchError):
        first.run_once()
    restarted, _, _ = batch_service(cache, api, index=index)
    restarted.run_once()
    assert api.output_reads == 1
    assert api.creations == 1
    assert restarted.status()["indexed_messages"] == 1


def test_application_lifespan_starts_worker_and_closes_clients(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    search, embeddings, index = search_service(cache)
    started = threading.Event()
    embeddings.on_embed = started.set
    app = create_app(tmp_path / "missing.yaml", environ={}, mail_search=search)
    with TestClient(app) as client:
        assert started.wait(2)
        assert client.get("/healthz").status_code == 200
    assert embeddings.closed and index.closed
    assert search.status()["worker"] == "stopped"


def test_mcp_search_runs_in_worker_and_disabled_status_is_available(tmp_path):
    cache, _ = cache_and_mail(tmp_path)
    search, _, _ = search_service(cache)
    search.run_once()
    server = create_mcp_server(None, mail_search=search)
    result = asyncio.run(server._handle_call_tool(None, CallToolRequestParams(name="semantic_search_emails", arguments={"query": "Abrechnung"})))
    assert not result.is_error
    assert result.structured_content["matches"][0]["uid"] == "42"
    disabled = create_mcp_server(None)
    result = asyncio.run(disabled._handle_call_tool(None, CallToolRequestParams(name="email_search_index_status", arguments={})))
    assert result.structured_content["configured"] is False
