# RAG Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local RAG knowledge base that retrieves relevant document chunks before DeepSeek answers, with user/group access control and source attribution.

**Architecture:** Documents are loaded from a configured local folder, split into stable chunks, indexed with a local SQLite FTS5 store, and retrieved by keyword relevance. Retrieved chunks are filtered by user/group scope and appended to the DeepSeek prompt. This first version avoids a heavyweight vector database while keeping the store replaceable.

**Tech Stack:** Python 3.12, SQLite FTS5, pathlib, existing `DeepSeekClient`, `AiReplyService`, `BotRuntime`, pytest.

---

### Task 1: Knowledge document ingestion and indexing

**Files:**
- Create: `app/services/knowledge_base.py`
- Create: `tests/test_knowledge_base.py`
- Modify: `requirements.txt` only if a parser dependency is required (plain text and Markdown require none).

- [ ] Write tests for UTF-8 Markdown ingestion, deterministic chunking, metadata retention, and FTS search.
- [ ] Run `py -3.12 -m pytest tests/test_knowledge_base.py -q` and verify RED.
- [ ] Implement `KnowledgeDocument`, `KnowledgeChunk`, and `KnowledgeBase` using SQLite tables `documents`, `chunks`, and FTS5 `chunks_fts`.
- [ ] Support `.md`, `.txt`, and `.markdown`; skip unsupported files.
- [ ] Store source path, title, chunk index, scope, and text; never store API keys.
- [ ] Re-run the focused tests and require GREEN.

### Task 2: Scoped retrieval and source formatting

**Files:**
- Modify: `app/services/knowledge_base.py`
- Create: `tests/test_knowledge_retrieval.py`

- [ ] Test that public chunks are visible to all users, private chunks only to their owner, and group chunks only to the matching group.
- [ ] Test that retrieval returns ranked chunks and source labels without leaking inaccessible chunks.
- [ ] Implement `search(query, user_id, group_id=None, limit=5)` with FTS5 ranking and explicit scope filtering.
- [ ] Implement source formatting with document name, section/chunk number, and local path.
- [ ] Re-run focused tests and require GREEN.

### Task 3: DeepSeek RAG prompt integration

**Files:**
- Modify: `app/services/reply_service.py`
- Create: `tests/test_rag_reply.py`

- [ ] Test that a normal question includes retrieved knowledge before the DeepSeek call.
- [ ] Test that no-result questions do not fabricate a knowledge citation.
- [ ] Test that direct comma replies, schedule commands, and weather handling keep their existing precedence.
- [ ] Add optional `knowledge_base` to `AiReplyService`; append retrieved chunks and source instructions to the user prompt.
- [ ] Preserve original user text in context storage while marking retrieved text as external reference material.
- [ ] Re-run focused tests and require GREEN.

### Task 4: Runtime configuration and WeChat command

**Files:**
- Modify: `app/main.py`
- Modify: `.env.example`
- Modify: `README.md`
- Create: `tests/test_knowledge_commands.py`

- [ ] Test `/知识库 重建`, `/知识库 搜索 <关键词>`, and normal messages through the runtime.
- [ ] Add `WX_BOT_KNOWLEDGE_DIR`, `WX_BOT_KNOWLEDGE_DB`, and `WX_BOT_KNOWLEDGE_SCOPE` configuration.
- [ ] Build the knowledge base at startup and pass it to `AiReplyService`.
- [ ] Permit the authorized administrator to rebuild the index; regular users can query only allowed scopes.
- [ ] Add startup and command documentation.
- [ ] Re-run focused tests and require GREEN.

### Task 5: End-to-end verification

**Files:**
- Modify: `tests/` only as needed for regression coverage.

- [ ] Run `py -3.12 -m pytest -q`.
- [ ] Run `py -3.12 -m compileall -q app tests`.
- [ ] Run `git diff --check`.
- [ ] Verify a local document question includes the document source in the AI prompt using a fake AI client.
- [ ] Verify no real chat content or API key is committed.
