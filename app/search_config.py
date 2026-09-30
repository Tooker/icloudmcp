from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class MailSearchConfig:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    model: str = "text-embedding-3-large"
    dimensions: int = 3072
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = field(default="", repr=False)
    collection_prefix: str = "icloud-mail"
    batch_size: int = 100
    poll_seconds: int = 30
    embedding_mode: str = "batch"


def load_mail_search_config(environ: dict[str, str] | None = None) -> MailSearchConfig:
    env = os.environ if environ is None else environ
    enabled = env.get("MAIL_SEARCH_ENABLED", "false").strip().casefold()
    if enabled not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ValueError("MAIL_SEARCH_ENABLED must be a boolean")
    model = env.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large").strip()
    maximum = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}.get(model)
    if maximum is None:
        raise ValueError("OPENAI_EMBEDDING_MODEL must be text-embedding-3-small or text-embedding-3-large")

    def integer(name: str, default: int, low: int, high: int) -> int:
        try:
            value = int(env.get(name) or str(default))
        except ValueError:
            raise ValueError(f"{name} must be an integer") from None
        if not low <= value <= high:
            raise ValueError(f"{name} must be between {low} and {high}")
        return value

    url = env.get("QDRANT_URL", "http://qdrant:6333").strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("QDRANT_URL must be an HTTP(S) URL without credentials, query or fragment")
    prefix = env.get("QDRANT_COLLECTION_PREFIX", "icloud-mail").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", prefix):
        raise ValueError("QDRANT_COLLECTION_PREFIX must contain 1–64 letters, digits, underscores or hyphens")
    mode = env.get("MAIL_SEARCH_EMBEDDING_MODE", "batch").strip().casefold()
    if mode not in {"batch", "standard"}:
        raise ValueError("MAIL_SEARCH_EMBEDDING_MODE must be batch or standard")
    return MailSearchConfig(
        enabled=enabled in {"true", "1", "yes", "on"},
        api_key=env.get("OPENAI_API_KEY", "").strip(),
        model=model,
        dimensions=integer("OPENAI_EMBEDDING_DIMENSIONS", maximum, 1, maximum),
        qdrant_url=url,
        qdrant_api_key=env.get("QDRANT_API_KEY", "").strip(),
        collection_prefix=prefix,
        batch_size=integer("MAIL_SEARCH_BATCH_SIZE", 100, 1, 1000),
        poll_seconds=integer("MAIL_SEARCH_POLL_SECONDS", 30, 1, 3600),
        embedding_mode=mode,
    )
