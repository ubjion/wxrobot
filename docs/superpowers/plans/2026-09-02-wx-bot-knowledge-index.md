# WeChat Bot Knowledge Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use the existing FTS5 index for ranked retrieval and replace destructive startup rebuilds with content-hash incremental synchronization.

**Architecture:** A `document_state` table tracks source hash and access metadata. Directory sync updates changed files, retains unchanged row IDs, and removes deleted sources. Search uses parameterized FTS5 MATCH plus bm25 ranking within the existing access-control filter.

**Tech Stack:** Python 3.13, SQLite FTS5, hashlib, pathlib, pytest.

---

### Task 1: Incremental directory synchronization

**Files:**
- Modify: `app/services/knowledge_base.py`
- Modify: `app/main.py`
- Modify: `tests/test_knowledge_base.py`

- [ ] Add failing tests proving a second unchanged sync returns zero changes and preserves chunk IDs, a changed file is reindexed, and a deleted file is removed.
- [ ] Run focused tests and verify RED.
- [ ] Add `document_state(source PRIMARY KEY, content_hash, scope, owner_id, group_id)` and SHA-256 hashing.
- [ ] Make `ingest_file` skip unchanged content/access metadata.
- [ ] Add `sync_directory()` to ingest changed supported files and delete missing documents under the synced root.
- [ ] Change startup from `rebuild()` to `sync_directory()`.
- [ ] Run focused/full tests; commit with `perf: incrementally sync knowledge documents`.

### Task 2: Ranked FTS retrieval

**Files:**
- Modify: `app/services/knowledge_base.py`
- Modify: `tests/test_knowledge_base.py`

- [ ] Add a failing ranking test where a chunk containing the query more often ranks before a weak match.
- [ ] Add punctuation and empty-token tests to prevent malformed MATCH expressions.
- [ ] Run focused tests and verify RED.
- [ ] Build a quoted OR expression from safe alphanumeric/CJK tokens. Join `chunks_fts` by rowid, apply the existing scope filter, and order by `bm25(chunks_fts)`.
- [ ] Fall back to parameterized LIKE only when tokenization yields no MATCH expression, not when FTS returns zero results.
- [ ] Run focused/full tests; commit with `perf: rank knowledge results with fts5`.

### Task 3: Verify knowledge stage

- [ ] Run pytest, compileall, `git diff --check`, and a temporary-database sync/search smoke test.
