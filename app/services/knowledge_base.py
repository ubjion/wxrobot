"""本地知识库导入、权限过滤和全文检索。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import sqlite3
from typing import Iterable


SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt"}
INDEX_VERSION = 2


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
                CREATE TABLE IF NOT EXISTS document_state (
                    source TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    owner_id TEXT,
                    group_id TEXT,
                    index_version INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(document_state)"
                ).fetchall()
            }
            if "index_version" not in columns:
                connection.execute(
                    "ALTER TABLE document_state ADD COLUMN "
                    "index_version INTEGER NOT NULL DEFAULT 0"
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
        source = str(path.resolve())
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunks = _split_text(text, self.chunk_size)
        with self._connect() as connection:
            state = connection.execute(
                "SELECT content_hash,scope,owner_id,group_id,index_version "
                "FROM document_state WHERE source=?",
                (source,),
            ).fetchone()
            if (
                state
                and state["content_hash"] == content_hash
                and state["scope"] == scope
                and state["owner_id"] == owner_id
                and state["group_id"] == group_id
                and state["index_version"] == INDEX_VERSION
            ):
                return 0
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
                    (
                        chunk_id,
                        _fts_text(chunk),
                        _fts_text(path.stem),
                        path.name,
                    ),
                )
            connection.execute(
                "INSERT INTO document_state(source,content_hash,scope,owner_id,group_id,index_version) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(source) DO UPDATE SET "
                "content_hash=excluded.content_hash, scope=excluded.scope, "
                "owner_id=excluded.owner_id, group_id=excluded.group_id, "
                "index_version=excluded.index_version",
                (source, content_hash, scope, owner_id, group_id, INDEX_VERSION),
            )
        return len(chunks)

    def sync_directory(
        self,
        directory: str | Path,
        scope: str = "public",
        owner_id: str | None = None,
        group_id: str | None = None,
    ) -> int:
        _validate_scope(scope, owner_id, group_id)
        root = Path(directory).resolve()
        files = {
            path.resolve()
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        }
        changed = 0
        with self._connect() as connection:
            rows = connection.execute("SELECT id,source FROM documents").fetchall()
            for row in rows:
                source = Path(row["source"]).resolve()
                if source.is_relative_to(root) and source not in files:
                    self._delete_document(connection, row["id"])
                    changed += 1
        for path in sorted(files):
            if self.ingest_file(path, scope, owner_id, group_id) > 0:
                changed += 1
        return changed

    def rebuild(self, directory: str | Path) -> int:
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks_fts")
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")
            connection.execute("DELETE FROM document_state")
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
        match_query = _fts_query(query)
        with self._connect() as connection:
            if match_query:
                rows = connection.execute(
                    """
                    SELECT c.id, d.title, d.source, c.text,
                           d.scope, d.owner_id, d.group_id
                    FROM chunks_fts
                    JOIN chunks c ON c.id=chunks_fts.rowid
                    JOIN documents d ON d.id=c.document_id
                    WHERE chunks_fts MATCH ?
                      AND (d.scope='public'
                        OR (d.scope='private' AND d.owner_id=?)
                        OR (d.scope='group' AND d.group_id=?))
                    ORDER BY bm25(chunks_fts), c.id DESC LIMIT ?
                    """,
                    (match_query, user_id, group_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT c.id, d.title, d.source, c.text,
                           d.scope, d.owner_id, d.group_id
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
        document = connection.execute(
            "SELECT source FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        chunk_ids = connection.execute(
            "SELECT id FROM chunks WHERE document_id=?", (document_id,)
        ).fetchall()
        for row in chunk_ids:
            connection.execute("DELETE FROM chunks_fts WHERE rowid=?", (row["id"],))
        connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        connection.execute("DELETE FROM documents WHERE id=?", (document_id,))
        if document:
            connection.execute(
                "DELETE FROM document_state WHERE source=?", (document["source"],)
            )


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


def _fts_text(text: str) -> str:
    """为默认 FTS5 tokenizer 补充中文单字和双字检索词。"""
    output: list[str] = []
    cursor = 0
    for match in re.finditer(r"[\u4e00-\u9fff]+", text):
        output.append(text[cursor:match.start()])
        chinese = match.group(0)
        terms = list(chinese)
        terms.extend(
            chinese[index:index + 2]
            for index in range(max(len(chinese) - 1, 0))
        )
        output.append(" " + " ".join(terms) + " ")
        cursor = match.end()
    output.append(text[cursor:])
    return "".join(output)


def _fts_query(query: str) -> str:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", query):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) <= 2:
                terms.append(token)
            else:
                terms.extend(
                    token[index:index + 2]
                    for index in range(len(token) - 1)
                )
        elif token.upper() not in {"AND", "OR", "NOT", "NEAR"}:
            terms.append(token)
    return " AND ".join(f'"{term}"' for term in dict.fromkeys(terms))
