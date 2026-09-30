from __future__ import annotations

import json
import sqlite3
from array import array
from contextlib import contextmanager
from typing import Any, Iterator

from app.icloud_cache import SQLiteICloudCalendarCache
from app.search_documents import PreparedMail
from app.timing import timed_phase


class SQLiteMailSearchStore:
    """Derived index state and reusable vectors alongside the original .eml BLOBs.

    Read source messages only within the active IMAP account. Expired cache
    snapshots remain searchable until invalidated; no IMAP request is made.
    UIDVALIDITY and source timestamps are checked again before publishing.
    """

    def __init__(self, cache: SQLiteICloudCalendarCache, index_id: str, embedding_id: str) -> None:
        if not cache.account_namespace:
            raise ValueError("Mail search requires an account-scoped SQLite cache")
        self.path = cache.path
        self.prefix = cache.account_namespace + "email_message:%"
        self.index_id = index_id
        self.embedding_id = embedding_id
        with self.connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS mail_search_documents (
                    index_id TEXT NOT NULL, document_key TEXT NOT NULL,
                    uid_validity TEXT NOT NULL, fetched_at REAL NOT NULL,
                    content_digest TEXT NOT NULL, ready INTEGER NOT NULL,
                    chunks INTEGER NOT NULL, skipped_attachments INTEGER NOT NULL,
                    truncated_sources INTEGER NOT NULL, skipped_messages INTEGER NOT NULL,
                    PRIMARY KEY(index_id, document_key)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS mail_search_embeddings (
                    embedding_id TEXT NOT NULL, text_digest TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    PRIMARY KEY(embedding_id, text_digest)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS mail_search_batches (
                    index_id TEXT PRIMARY KEY, job_json TEXT NOT NULL
                )
            """)

    @timed_phase("sqlite_batch_status")
    def batch_job(self) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT job_json FROM mail_search_batches WHERE index_id = ?", (self.index_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_batch_job(self, job: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute("INSERT OR REPLACE INTO mail_search_batches VALUES (?, ?)", (self.index_id, json.dumps(job)))

    def clear_batch_job(self) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM mail_search_batches WHERE index_id = ?", (self.index_id,))

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 10000")
            yield connection
            connection.commit()
        finally:
            connection.close()

    # Empty/legacy UID generations have no reliable original-mail reference.
    _VALID_SOURCE = "e.uid_validity != '' AND (m.uid_validity IS NULL OR m.uid_validity = e.uid_validity)"
    _CURRENT_INDEX = "s.ready = 1 AND s.uid_validity = e.uid_validity AND s.fetched_at = e.fetched_at"

    def pending(self, limit: int) -> list[str]:
        with self.connection() as connection:
            rows = connection.execute(f"""
                SELECT e.cache_key FROM email_messages e
                LEFT JOIN mailbox_states m ON m.mailbox_key = e.mailbox_key
                LEFT JOIN mail_search_documents s ON s.document_key = e.cache_key AND s.index_id = ?
                WHERE e.cache_key LIKE ? AND {self._VALID_SOURCE}
                AND (s.document_key IS NULL OR NOT ({self._CURRENT_INDEX}))
                ORDER BY e.fetched_at DESC, e.cache_key LIMIT ?
            """, (self.index_id, self.prefix, limit)).fetchall()
        return [row[0] for row in rows]

    def load(self, document_key: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(f"""
                SELECT e.cache_key AS document_key, e.mailbox, e.uid, e.uid_validity,
                       e.fetched_at, e.summary_json,
                       CASE WHEN length(e.raw_message) <= 25000000 THEN e.raw_message ELSE NULL END AS raw_message
                FROM email_messages e LEFT JOIN mailbox_states m ON m.mailbox_key = e.mailbox_key
                WHERE e.cache_key = ? AND e.cache_key LIKE ? AND {self._VALID_SOURCE}
            """, (document_key, self.prefix)).fetchone()
        if row is None:
            return None
        document = dict(row)
        try:
            summary = json.loads(document.pop("summary_json"))
        except ValueError:
            summary = {}
        document["summary"] = summary if isinstance(summary, dict) else {}
        return document

    def state(self, document_key: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM mail_search_documents WHERE index_id = ? AND document_key = ?", (self.index_id, document_key)).fetchone()
        return dict(row) if row else None

    def is_current(self, document: dict[str, Any], connection: sqlite3.Connection | None = None) -> bool:
        if connection is None:
            with self.connection() as own:
                return self.is_current(document, own)
        row = connection.execute(f"""
            SELECT 1 FROM email_messages e LEFT JOIN mailbox_states m ON m.mailbox_key = e.mailbox_key
            WHERE e.cache_key = ? AND e.cache_key LIKE ? AND e.uid_validity = ? AND e.fetched_at = ?
                  AND {self._VALID_SOURCE}
        """, (document["document_key"], self.prefix, document["uid_validity"], document["fetched_at"])).fetchone()
        return row is not None

    def save(self, document: dict[str, Any], digest: str, prepared: PreparedMail, *, ready: bool) -> bool:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not self.is_current(document, connection):
                return False
            connection.execute("""
                INSERT OR REPLACE INTO mail_search_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (self.index_id, document["document_key"], document["uid_validity"], document["fetched_at"], digest,
                  int(ready), len(prepared.chunks), prepared.skipped_attachments, prepared.truncated_sources, prepared.skipped_messages))
        return True

    def refresh_unchanged(self, document: dict[str, Any], state: dict[str, Any]) -> bool:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not self.is_current(document, connection):
                return False
            connection.execute("UPDATE mail_search_documents SET fetched_at = ? WHERE index_id = ? AND document_key = ? AND content_digest = ? AND ready = 1",
                               (document["fetched_at"], self.index_id, document["document_key"], state["content_digest"]))
        return True

    def stale(self, limit: int) -> list[str]:
        with self.connection() as connection:
            rows = connection.execute(f"""
                SELECT s.document_key FROM mail_search_documents s
                LEFT JOIN email_messages e ON e.cache_key = s.document_key
                LEFT JOIN mailbox_states m ON m.mailbox_key = e.mailbox_key
                WHERE s.index_id = ? AND (e.cache_key IS NULL OR s.uid_validity != e.uid_validity OR NOT ({self._VALID_SOURCE}))
                LIMIT ?
            """, (self.index_id, limit)).fetchall()
        return [row[0] for row in rows]

    def remove(self, document_key: str) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM mail_search_documents WHERE index_id = ? AND document_key = ?", (self.index_id, document_key))

    def reset_documents(self) -> None:
        # Retain embeddings when rebuilding a lost Qdrant collection.
        with self.connection() as connection:
            connection.execute("DELETE FROM mail_search_documents WHERE index_id = ?", (self.index_id,))

    @timed_phase("sqlite_embedding_read")
    def get_vector(self, text_digest: str, dimensions: int) -> list[float] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT vector FROM mail_search_embeddings WHERE embedding_id = ? AND text_digest = ?", (self.embedding_id, text_digest)).fetchone()
        if row is None or len(row[0]) != dimensions * 4:
            return None
        vector = array("f")
        vector.frombytes(row[0])
        return vector.tolist()

    def save_vectors(self, vectors: list[tuple[str, list[float]]]) -> None:
        with self.connection() as connection:
            connection.executemany("INSERT OR REPLACE INTO mail_search_embeddings VALUES (?, ?, ?)",
                                   [(self.embedding_id, digest, array("f", vector).tobytes()) for digest, vector in vectors])

    @timed_phase("sqlite_search_source_check")
    def current_summary(self, document_key: str, digest: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(f"""
                SELECT e.summary_json, e.uid, e.mailbox, e.uid_validity FROM email_messages e
                JOIN mail_search_documents s ON s.document_key = e.cache_key AND s.index_id = ?
                LEFT JOIN mailbox_states m ON m.mailbox_key = e.mailbox_key
                WHERE e.cache_key = ? AND e.cache_key LIKE ? AND s.content_digest = ?
                      AND {self._VALID_SOURCE} AND {self._CURRENT_INDEX}
            """, (self.index_id, document_key, self.prefix, digest)).fetchone()
        if row is None:
            return None
        try:
            summary = json.loads(row[0])
        except ValueError:
            summary = {}
        if not isinstance(summary, dict):
            summary = {}
        return {**summary, "uid": row[1], "mailbox": row[2], "uid_validity": row[3]}

    @timed_phase("sqlite_search_status")
    def status(self) -> dict[str, int]:
        with self.connection() as connection:
            row = connection.execute(f"""
                SELECT COUNT(*) AS cached_messages,
                       COALESCE(SUM(CASE WHEN {self._CURRENT_INDEX} THEN 1 ELSE 0 END), 0) AS indexed_messages,
                       COALESCE(SUM(CASE WHEN {self._CURRENT_INDEX} THEN s.chunks ELSE 0 END), 0) AS indexed_chunks,
                       COALESCE(SUM(CASE WHEN {self._CURRENT_INDEX} THEN s.skipped_attachments ELSE 0 END), 0) AS skipped_attachments,
                       COALESCE(SUM(CASE WHEN {self._CURRENT_INDEX} THEN s.truncated_sources ELSE 0 END), 0) AS truncated_sources,
                       COALESCE(SUM(CASE WHEN {self._CURRENT_INDEX} THEN s.skipped_messages ELSE 0 END), 0) AS skipped_messages
                FROM email_messages e LEFT JOIN mailbox_states m ON m.mailbox_key = e.mailbox_key
                LEFT JOIN mail_search_documents s ON s.document_key = e.cache_key AND s.index_id = ?
                WHERE e.cache_key LIKE ? AND {self._VALID_SOURCE}
            """, (self.index_id, self.prefix)).fetchone()
        result = dict(row)
        result["pending_messages"] = result["cached_messages"] - result["indexed_messages"]
        return result
