"""本地知识库导入、权限过滤和全文检索。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Iterable


SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class KnowledgeChunk:
    id: int
    title: str
    source: str
    text: str
    scope: str
    owner_id: str | None = None
    group_id: str | None = None


class KnowledgeBase:
    def __init__(self, db_path: str | Path, chunk_size: int = 800) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.db_path = Path(db_path)
        self.chunk_size = chunk_size
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    owner_id TEXT,
                    group_id TEXT
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    text, title, source
                );
                """
            )

    def ingest_directory(
        self,
        directory: str | Path,
        scope: str = "public",
        owner_id: str | None = None,
        group_id: str | None = None,
    ) -> int:
        root = Path(directory)
        count = 0
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                count += self.ingest_file(path, scope, owner_id, group_id)
        return count

    def ingest_file(
        self,
        path: str | Path,
        scope: str = "public",
        owner_id: str | None = None,
        group_id: str | None = None,
    ) -> int:
        _validate_scope(scope, owner_id, group_id)
        path = Path(path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return 0
        text = path.read_text(encoding="utf-8")
        source = str(path)
        chunks = _split_text(text, self.chunk_size)
        with self._connect() as connection:
            old = connection.execute(
                "SELECT id FROM documents WHERE source=?", (source,)
            ).fetchone()
            if old:
                self._delete_document(connection, old["id"])
            document_id = connection.execute(
                "INSERT INTO documents(source,title,scope,owner_id,group_id) VALUES(?,?,?,?,?)",
                (source, path.stem, scope, owner_id, group_id),
            ).lastrowid
            for index, chunk in enumerate(chunks):
                chunk_id = connection.execute(
                    "INSERT INTO chunks(document_id,chunk_index,text) VALUES(?,?,?)",
                    (document_id, index, chunk),
                ).lastrowid
                connection.execute(
                    "INSERT INTO chunks_fts(rowid,text,title,source) VALUES(?,?,?,?)",
                    (chunk_id, chunk, path.stem, path.name),
                )
        return len(chunks)

    def rebuild(self, directory: str | Path) -> int:
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks_fts")
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")
        return self.ingest_directory(directory)

    def search(
        self,
        query: str,
        user_id: str,
        group_id: str | None = None,
        limit: int = 5,
    ) -> list[KnowledgeChunk]:
        query = query.strip()
        if not query or limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, d.title, d.source, c.text, d.scope, d.owner_id, d.group_id
                FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE (d.scope='public'
                    OR (d.scope='private' AND d.owner_id=?)
                    OR (d.scope='group' AND d.group_id=?))
                  AND c.text LIKE ?
                ORDER BY c.id DESC LIMIT ?
                """,
                (user_id, group_id, f"%{query}%", limit),
            ).fetchall()
        return [
            KnowledgeChunk(**{**dict(row), "source": Path(row["source"]).name})
            for row in rows
        ]

    def _delete_document(self, connection: sqlite3.Connection, document_id: int) -> None:
        chunk_ids = connection.execute(
            "SELECT id FROM chunks WHERE document_id=?", (document_id,)
        ).fetchall()
        for row in chunk_ids:
            connection.execute("DELETE FROM chunks_fts WHERE rowid=?", (row["id"],))
        connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        connection.execute("DELETE FROM documents WHERE id=?", (document_id,))


def _validate_scope(scope: str, owner_id: str | None, group_id: str | None) -> None:
    if scope not in {"public", "private", "group"}:
        raise ValueError("scope must be public, private, or group")
    if scope == "private" and not owner_id:
        raise ValueError("private scope requires owner_id")
    if scope == "group" and not group_id:
        raise ValueError("group scope requires group_id")


def _split_text(text: str, chunk_size: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size and len(current) + len(paragraph) + 1 <= chunk_size:
            current = f"{current}\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > chunk_size:
            chunks.append(paragraph[:chunk_size])
            paragraph = paragraph[chunk_size:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks
