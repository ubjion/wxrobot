# WeChat Bot Search Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce latency and external-search cost by searching only for explicit or time-sensitive requests while preserving safe failure behavior.

**Architecture:** A deterministic intent predicate gates Firecrawl. Stable knowledge and casual messages go directly to RAG/AI; explicit search and freshness queries require web results and continue to fail closed when no trustworthy current source is available.

**Tech Stack:** Python 3.13, regex/string matching, pytest.

---

### Task 1: Gate web search by intent

**Files:**
- Modify: `app/services/reply_service.py`
- Modify: `tests/test_reply_service.py`

- [ ] Change the existing “every text searches” test into a failing test that `牛顿是谁` skips the web client and still calls AI.
- [ ] Add parameterized tests for explicit search and freshness terms such as `搜索`, `最新`, `新闻`, `官网`, `价格`, `实时`, and `今天`.
- [ ] Run focused tests and verify RED.
- [ ] Implement `_is_search_query()` using explicit-search and freshness markers. Keep weather routing first.
- [ ] Run focused/full tests; commit with `perf: search only when current sources are needed`.

### Task 2: Bound external context and document degradation

**Files:**
- Modify: `app/services/reply_service.py`
- Modify: `tests/test_reply_service.py`
- Modify: `README.md`

- [ ] Add failing tests that external titles/descriptions are length-limited and delimited as untrusted reference data.
- [ ] Implement one formatter used by normal and weather search paths, limiting title to 200 characters, URL to 500, description to 1000, and total search context to 6000 characters.
- [ ] Update README: casual/stable questions work without Firecrawl; explicit current-information requests report search unavailability rather than guessing.
- [ ] Run focused/full tests and commit with `feat: bound untrusted search context`.

### Task 3: Verify search stage

- [ ] Run full pytest, compileall, and `git diff --check`.
