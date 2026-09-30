from __future__ import annotations

import hashlib
import threading
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from loguru import logger

from app.batch_embeddings import BatchEmbeddingsNeeded, MAX_BATCH_INPUTS, OpenAIBatchEmbeddings
from app.icloud_cache import SQLiteICloudCalendarCache
from app.imap import IMAPServiceError
from app.search_clients import MailSearchError, OpenAIEmbeddings, QdrantMailIndex
from app.search_config import MailSearchConfig
from app.search_documents import PIPELINE_VERSION, PreparedMail, prepare_mail
from app.search_store import SQLiteMailSearchStore
from app.timing import measure_phase


def _digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


class SemanticMailSearch:
    def __init__(self, cache: SQLiteICloudCalendarCache, config: MailSearchConfig, *, embeddings: Any = None, index: Any = None) -> None:
        self.config = config
        embedding_id = _digest(f"{cache.account_namespace}|{config.model}|{config.dimensions}")
        collection_id = _digest(f"{embedding_id}|{PIPELINE_VERSION}")
        self.collection = f"{config.collection_prefix}-{collection_id[:16]}"
        self.store = SQLiteMailSearchStore(cache, _digest(f"{config.qdrant_url}|{self.collection}"), embedding_id)
        self.embeddings = embeddings if embeddings is not None else OpenAIEmbeddings(config)
        self.index = index if index is not None else QdrantMailIndex(config, self.collection)
        self._stop = threading.Event()
        self.batch = OpenAIBatchEmbeddings(self.embeddings.client, config, self.store, self._stop) if config.embedding_mode == "batch" else None
        self._index_lock = threading.Lock()
        self._started = False
        self._worker_state = "idle"
        self._last_error: str | None = None

    def run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            try:
                self._worker_state = "indexing"
                progress = self.run_once()
                self._worker_state = "waiting_batch" if self.store.batch_job() else "idle"
                self._last_error = None
                failures = 0
                delay = 0.1 if progress["processed"] or progress["removed"] else self.config.poll_seconds
            except Exception as exc:
                self._worker_state = "retrying"
                self._last_error = str(exc) if isinstance(exc, MailSearchError) else "Background indexing failed; retrying."
                failures += 1
                delay = min(300, self.config.poll_seconds * 2 ** min(failures - 1, 4))
                logger.warning("mail_search action=index status=retry error_type={} retry_seconds={}", type(exc).__name__, delay)
            self._stop.wait(delay)
        self._worker_state = "stopped"

    def stop(self) -> None:
        self._stop.set()
        stop = getattr(self.index, "stop", None)
        if callable(stop):
            stop()

    def close(self) -> None:
        self.embeddings.close()
        self.index.close()

    def run_once(self) -> dict[str, int]:
        with self._index_lock:
            created, point_count = self.index.ensure_collection()
            if created or (not self._started and point_count < self.store.status()["indexed_chunks"]):
                self.store.reset_documents()
            self._started = True
            removed = 0
            for document_key in self.store.stale(self.config.batch_size):
                if self._stop.is_set():
                    break
                self.index.delete_document(document_key)
                self.store.remove(document_key)
                removed += 1
            if self.batch is not None and self.batch.resume():
                return {"processed": 0, "removed": removed}
            processed = 0
            batch_inputs: dict[str, str] = {}
            for document_key in self.store.pending(self.config.batch_size):
                if self._stop.is_set():
                    break
                document = self.store.load(document_key)
                if document is None:
                    continue
                try:
                    self._index_document(document)
                    processed += 1
                except BatchEmbeddingsNeeded as needed:
                    for digest, text in needed.inputs.items():
                        if len(batch_inputs) < MAX_BATCH_INPUTS:
                            batch_inputs[digest] = text
                    if len(batch_inputs) >= MAX_BATCH_INPUTS:
                        break
            if batch_inputs and not self._stop.is_set():
                self.batch.enqueue(batch_inputs)
                self.batch.resume()
            if processed or removed:
                logger.info("mail_search action=index status=ok processed={} removed={}", processed, removed)
            return {"processed": processed, "removed": removed}

    def _index_document(self, document: dict[str, Any]) -> None:
        digest = _digest(document["raw_message"] or b"")
        state = self.store.state(document["document_key"])
        if state and state["ready"] and state["content_digest"] == digest and state["uid_validity"] == document["uid_validity"]:
            self.store.refresh_unchanged(document, state)
            return
        try:
            prepared = prepare_mail(document)
        except (IMAPServiceError, ValueError, TypeError):
            prepared = PreparedMail([], skipped_messages=1)
        vectors = self._vectors([chunk["embedding_text"] for chunk in prepared.chunks], background=True)
        if self._stop.is_set() or not self.store.save(document, digest, prepared, ready=False):
            return
        points = []
        for number, (chunk, vector) in enumerate(zip(prepared.chunks, vectors, strict=True)):
            points.append({
                "id": str(uuid5(NAMESPACE_URL, f"{self.store.index_id}|{document['document_key']}|{document['uid_validity']}|{digest}|{number}")),
                "vector": vector,
                "payload": {
                    "document_key": document["document_key"], "content_digest": digest,
                    "mailbox": document["mailbox"], "source": chunk["source"],
                    "attachment_id": chunk["attachment_id"], "filename": chunk["filename"],
                    "chunk": number, "text": chunk["text"],
                },
            })
        # Staging is durable before Qdrant writes, so interrupted/partial writes
        # are retried and removed even when the source is invalidated meanwhile.
        self.index.replace_document(document["document_key"], points)
        if not self.store.save(document, digest, prepared, ready=True):
            self.index.delete_document(document["document_key"])
            self.store.remove(document["document_key"])

    def _vectors(self, texts: list[str], *, background: bool = False) -> list[list[float]]:
        digests = [_digest(text) for text in texts]
        vectors = {digest: self.store.get_vector(digest, self.config.dimensions) for digest in set(digests)}
        missing = list(dict.fromkeys(digest for digest in digests if vectors[digest] is None))
        by_digest = dict(zip(digests, texts))
        if background and self.batch is not None and missing:
            raise BatchEmbeddingsNeeded({digest: by_digest[digest] for digest in missing})
        for offset in range(0, len(missing), 16):
            batch = missing[offset:offset + 16]
            if self._stop.is_set():
                raise MailSearchError("Mail search is shutting down.")
            with measure_phase("openai_query_embedding"):
                values = self.embeddings.embed([by_digest[digest] for digest in batch])
            if len(values) != len(batch):
                raise MailSearchError("Embedding provider returned incomplete vectors.")
            self.store.save_vectors(list(zip(batch, values, strict=True)))
            vectors.update(zip(batch, values, strict=True))
        return [vectors[digest] for digest in digests]

    def status(self) -> dict[str, Any]:
        job = self.store.batch_job()
        return {
            "configured": True, "model": self.config.model, "dimensions": self.config.dimensions,
            "worker": self._worker_state, "source": "sqlite_cached_emails",
            "embedding_mode": self.config.embedding_mode,
            "last_error": self._last_error,
            "batch": {"status": job["phase"], "inputs": len(job["inputs"]), "id": job.get("batch_id")} if job else None,
            **self.store.status(),
        }

    def search(self, query: str, *, mailbox: str | None = None, source: str | None = None, limit: int = 10) -> dict[str, Any]:
        query = query.strip()
        if not query or len(query.encode("utf-8")) > 4000:
            raise ValueError("query must contain 1–4000 UTF-8 bytes")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if source not in {None, "body", "attachment"}:
            raise ValueError("source must be body or attachment")
        if mailbox is not None and (not mailbox.strip() or len(mailbox) > 1000):
            raise ValueError("mailbox must contain 1–1000 characters")
        status = self.status()
        if not status["indexed_chunks"]:
            return {"matches": [], "index": status}
        vector = self._vectors([query])[0]
        with measure_phase("qdrant_search"):
            hits = self.index.search(vector, mailbox=mailbox, source=source, limit=min(500, limit * 10))
        matches = []
        seen = set()
        for hit in hits:
            payload = hit.get("payload") or {}
            key = payload.get("document_key", "")
            summary = self.store.current_summary(key, payload.get("content_digest", ""))
            if summary is None:
                continue
            identity = (key, payload.get("source"), payload.get("attachment_id"))
            if identity in seen:
                continue
            seen.add(identity)
            matches.append({
                **summary, "score": hit["score"], "source": payload.get("source"),
                "attachment_id": payload.get("attachment_id"), "filename": payload.get("filename"),
                "chunk": payload.get("chunk"), "excerpt": str(payload.get("text") or "")[:2000],
                "email": {"tool": "get_email", "arguments": {"mailbox": summary["mailbox"], "uid": summary["uid"], "expected_uid_validity": summary["uid_validity"]}},
                "attachment": {"tool": "get_email_attachment", "arguments": {"mailbox": summary["mailbox"], "uid": summary["uid"], "attachment_id": payload["attachment_id"], "expected_uid_validity": summary["uid_validity"]}} if payload.get("attachment_id") else None,
            })
            if len(matches) >= limit:
                break
        return {"matches": matches, "index": status}
