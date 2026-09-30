from __future__ import annotations

import json
import math
import threading
from typing import Any
from uuid import uuid4

import httpx
from loguru import logger

from app.search_clients import MailSearchError, _json_request
from app.search_config import MailSearchConfig
from app.search_store import SQLiteMailSearchStore

MAX_BATCH_INPUTS = 1000


class BatchEmbeddingsNeeded(Exception):
    def __init__(self, inputs: dict[str, str]) -> None:
        self.inputs = inputs
        super().__init__("Background embeddings pending")


class OpenAIBatchEmbeddings:
    """One durable Batch job at a time; never resubmit a known remote job.

    custom_id is the input's hash, so reordered and partially successful output
    is mapped to the correct vector. Only absent vectors are submitted again.
    """

    def __init__(self, client: httpx.Client, config: MailSearchConfig, store: SQLiteMailSearchStore, stop: threading.Event) -> None:
        self.client = client
        self.config = config
        self.store = store
        self.stop = stop

    def enqueue(self, inputs: dict[str, str]) -> None:
        if not inputs or len(inputs) > MAX_BATCH_INPUTS or self.store.batch_job() is not None:
            raise ValueError("Invalid or overlapping embedding batch")
        self.store.save_batch_job({"local_id": uuid4().hex, "phase": "queued", "inputs": inputs})

    def resume(self) -> bool:
        """Return True while waiting; save vectors before clearing a terminal job."""
        job = self.store.batch_job()
        if job is None:
            return False
        if self.stop.is_set():
            return True
        if "input_file_id" not in job:
            lines = [json.dumps({
                "custom_id": digest, "method": "POST", "url": "/v1/embeddings",
                "body": {"model": self.config.model, "dimensions": self.config.dimensions,
                         "input": text, "encoding_format": "float"},
            }, ensure_ascii=False) for digest, text in job["inputs"].items()]
            uploaded = _json_request(self.client, "POST", "files", data={"purpose": "batch"},
                                     files={"file": ("mail-embeddings.jsonl", ("\n".join(lines) + "\n").encode("utf-8"), "application/jsonl")})
            if not isinstance(uploaded.get("id"), str):
                raise MailSearchError("Batch input upload returned an invalid file ID.")
            job.update(input_file_id=uploaded["id"], phase="uploaded")
            self.store.save_batch_job(job)
        if self.stop.is_set():
            return True
        if "batch_id" not in job:
            if job["phase"] == "submitting":
                # A timeout/restart after POST may leave an accepted, billable
                # job. Recover by metadata rather than blindly submitting again.
                remote = self._find_remote_job(job["local_id"])
                if remote is None:
                    raise MailSearchError("Batch submission is uncertain; check OpenAI Platform batches before retrying.")
            else:
                job["phase"] = "submitting"
                self.store.save_batch_job(job)
                try:
                    remote = _json_request(self.client, "POST", "batches", json={
                        "input_file_id": job["input_file_id"], "endpoint": "/v1/embeddings",
                        "completion_window": "24h", "metadata": {"icloud_job": job["local_id"]},
                    })
                except MailSearchError as exc:
                    if exc.status_code is not None and 400 <= exc.status_code < 500 and exc.status_code != 408:
                        job["phase"] = "uploaded"
                        self.store.save_batch_job(job)
                    # Preserve the uncertain phase for restart-safe recovery.
                    raise
            if not isinstance(remote.get("id"), str):
                raise MailSearchError("Batch submission returned an invalid batch ID.")
            job.update(batch_id=remote["id"], phase=remote.get("status", "validating"))
            self.store.save_batch_job(job)
            logger.info("mail_search action=batch_submit status=ok inputs={}", len(job["inputs"]))
            return True
        remote = _json_request(self.client, "GET", "batches/" + job["batch_id"])
        phase = remote.get("status")
        if phase not in {"validating", "in_progress", "finalizing", "completed", "failed", "expired", "cancelling", "cancelled"}:
            raise MailSearchError("Batch provider returned an invalid status.")
        job["phase"] = phase
        self.store.save_batch_job(job)
        if phase not in {"completed", "failed", "expired", "cancelled"}:
            return True
        if not job.get("ingested"):
            if remote.get("output_file_id"):
                self._ingest(remote["output_file_id"], job["inputs"])
            job["ingested"] = True
            self.store.save_batch_job(job)
        # Keep the job until cleanup succeeds, so a restart does not upload
        # another copy. A repeated ingestion only overwrites the same vectors.
        for file_id in dict.fromkeys([job["input_file_id"], remote.get("output_file_id"), remote.get("error_file_id")]):
            if self.stop.is_set():
                return True
            if file_id:
                self._delete_file(file_id)
        self.store.clear_batch_job()
        logger.info("mail_search action=batch_complete status={} inputs={}", phase, len(job["inputs"]))
        if phase != "completed":
            raise MailSearchError("Embedding batch did not fully complete; successful vectors were retained.")
        return False

    def _find_remote_job(self, local_id: str) -> dict[str, Any] | None:
        after = None
        for _ in range(100):
            if self.stop.is_set():
                return None
            params: dict[str, Any] = {"limit": 100}
            if after:
                params["after"] = after
            page = _json_request(self.client, "GET", "batches", params=params)
            rows = page.get("data", [])
            for remote in rows:
                if (remote.get("metadata") or {}).get("icloud_job") == local_id:
                    return remote
            if not page.get("has_more") or not rows:
                return None
            after = rows[-1]["id"]
        return None

    def _ingest(self, file_id: str, expected: dict[str, str]) -> None:
        try:
            with self.client.stream("GET", "files/" + file_id + "/content") as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if self.stop.is_set():
                        raise MailSearchError("Mail search is shutting down.")
                    if not line.strip():
                        continue
                    result = json.loads(line)
                    digest = result["custom_id"]
                    if digest not in expected:
                        raise ValueError()
                    if result.get("error") or not result.get("response") or result["response"]["status_code"] != 200:
                        continue
                    values = result["response"]["body"]["data"]
                    if len(values) != 1 or values[0]["index"] != 0:
                        raise ValueError()
                    vector = values[0]["embedding"]
                    if len(vector) != self.config.dimensions or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
                        raise ValueError()
                    self.store.save_vectors([(digest, vector)])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise MailSearchError("Embedding batch output could not be read safely.") from None

    def _delete_file(self, file_id: str) -> None:
        try:
            response = self.client.delete("files/" + file_id)
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPError:
            raise MailSearchError("Embedding batch file cleanup failed.") from None
