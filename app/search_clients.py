from __future__ import annotations

import math
import threading
from typing import Any

import httpx

from app.search_config import MailSearchConfig


class MailSearchError(RuntimeError):
    """Only safe, application-owned messages may cross the MCP boundary."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _json_request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = client.request(method, url, **kwargs)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in {401, 403}:
            raise MailSearchError("Search provider authentication failed; check its API key.", status_code=code) from None
        if code == 429:
            raise MailSearchError("Search provider rate limit or quota reached; retry later.", status_code=code) from None
        raise MailSearchError("Search provider request failed.", status_code=code) from None
    except (httpx.HTTPError, ValueError):
        raise MailSearchError("Search provider is unavailable or returned an invalid response.") from None


class OpenAIEmbeddings:
    def __init__(self, config: MailSearchConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        # Fixed HTTPS destination; an API key cannot be forwarded to a configured search host.
        self.client = httpx.Client(
            base_url="https://api.openai.com/v1/",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=httpx.Timeout(30, connect=5),
            transport=transport,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or len(texts) > 16 or any(not text.strip() or len(text.encode("utf-8")) > 6500 for text in texts):
            raise ValueError("Embedding batches require 1–16 non-empty texts of at most 6500 UTF-8 bytes")
        result = _json_request(self.client, "POST", "embeddings", json={
            "model": self.config.model, "dimensions": self.config.dimensions,
            "input": texts, "encoding_format": "float",
        })
        try:
            data = result["data"]
            if len(data) != len(texts) or sorted(item["index"] for item in data) != list(range(len(texts))):
                raise ValueError()
            vectors = [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]
            if any(len(vector) != self.config.dimensions or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector) for vector in vectors):
                raise ValueError()
            return vectors
        except (KeyError, TypeError, ValueError):
            raise MailSearchError("Embedding provider returned invalid vectors.") from None

    def close(self) -> None:
        self.client.close()


class QdrantMailIndex:
    def __init__(self, config: MailSearchConfig, collection: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self.collection = collection
        self.path = f"collections/{collection}"
        self._stop = threading.Event()
        self.client = httpx.Client(
            base_url=config.qdrant_url + "/",
            headers={"api-key": config.qdrant_api_key} if config.qdrant_api_key else {},
            timeout=httpx.Timeout(30, connect=5),
            transport=transport,
        )

    def ensure_collection(self) -> tuple[bool, int]:
        self._check_stop()
        try:
            response = self.client.get(self.path)
        except httpx.HTTPError:
            raise MailSearchError("Qdrant is unavailable.") from None
        created = response.status_code == 404
        if created:
            self._check_stop()
            _json_request(self.client, "PUT", self.path, json={
                "vectors": {"size": self.config.dimensions, "distance": "Cosine", "on_disk": True},
                "on_disk_payload": True,
            })
            return True, 0
        try:
            response.raise_for_status()
            result = response.json()["result"]
            vectors = result["config"]["params"]["vectors"]
            if vectors["size"] != self.config.dimensions or vectors["distance"] != "Cosine":
                raise MailSearchError("Qdrant collection has incompatible vector settings.")
            return False, int(result.get("points_count") or 0)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            raise MailSearchError("Qdrant collection could not be read.") from None

    def replace_document(self, document_key: str, points: list[dict[str, Any]]) -> None:
        self._check_stop()
        self.delete_document(document_key)
        for offset in range(0, len(points), 16):
            self._check_stop()
            _json_request(self.client, "PUT", self.path + "/points", params={"wait": "true"}, json={"points": points[offset:offset + 16]})

    def delete_document(self, document_key: str) -> None:
        self._check_stop()
        _json_request(self.client, "POST", self.path + "/points/delete", params={"wait": "true"}, json={
            "filter": {"must": [{"key": "document_key", "match": {"value": document_key}}]},
        })

    def search(self, vector: list[float], *, mailbox: str | None, source: str | None, limit: int) -> list[dict[str, Any]]:
        conditions = []
        if mailbox is not None:
            conditions.append({"key": "mailbox", "match": {"value": mailbox}})
        if source is not None:
            conditions.append({"key": "source", "match": {"value": source}})
        body: dict[str, Any] = {"query": vector, "limit": limit, "with_payload": True, "with_vector": False}
        if conditions:
            body["filter"] = {"must": conditions}
        result = _json_request(self.client, "POST", self.path + "/points/query", json=body)
        try:
            points = result["result"]["points"]
            if not isinstance(points, list):
                raise ValueError()
            return points
        except (KeyError, TypeError, ValueError):
            raise MailSearchError("Qdrant returned invalid search results.") from None

    def close(self) -> None:
        self.client.close()

    def stop(self) -> None:
        self._stop.set()

    def _check_stop(self) -> None:
        if self._stop.is_set():
            raise MailSearchError("Mail search is shutting down.")
