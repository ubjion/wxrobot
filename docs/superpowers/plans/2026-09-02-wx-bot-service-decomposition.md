# WeChat Bot Service Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `AiReplyService` responsibilities and repeated session-discovery work without changing externally visible reply behavior.

**Architecture:** Pure intent/parsing/formatting logic moves to `reply_routing.py`. Concurrent local/web reference collection moves to `reference_context.py` and returns a typed result. MessageReader refreshes dynamic sessions on a configurable interval instead of every poll.

**Tech Stack:** Python 3.13, dataclasses, concurrent futures, pytest.

---

### Task 1: Extract reply routing utilities

**Files:**
- Create: `app/services/reply_routing.py`
- Create: `tests/test_reply_routing.py`
- Modify: `app/services/reply_service.py`

- [ ] Add failing direct tests for weather detection/city extraction, web-search intent, and bounded external-result formatting.
- [ ] Implement pure functions `is_weather_query`, `extract_weather_city`, `should_search_web`, and `format_web_results`.
- [ ] Replace `AiReplyService` private implementations with imported functions; run all existing reply tests.
- [ ] Commit with `refactor: extract reply routing utilities`.

### Task 2: Extract concurrent reference context builder

**Files:**
- Create: `app/services/reference_context.py`
- Create: `tests/test_reference_context.py`
- Modify: `app/services/reply_service.py`

- [ ] Add failing tests for parallel knowledge/web collection, knowledge-only degradation, required-search failure, and empty required-search results.
- [ ] Implement frozen `ReferenceContextResult(context, error_reply)` and `ReferenceContextBuilder.build(event, content)`.
- [ ] Move concurrency, source formatting, and retrieval timing logs out of `AiReplyService`.
- [ ] Keep context limits and current Chinese user-facing errors unchanged.
- [ ] Run full tests; commit with `refactor: extract reference context builder`.

### Task 3: Throttle dynamic session discovery

**Files:**
- Modify: `app/messages/reader.py`
- Modify: `tests/test_message_reader.py`
- Modify: `.env.example`
- Modify: `app/main.py`

- [ ] Add a failing clock-driven test proving repeated polls within the refresh interval call `user_provider` once.
- [ ] Add `user_refresh_interval` and monotonic clock dependencies to `MessageReader`; default refresh interval 30 seconds.
- [ ] Add `WX_BOT_USER_REFRESH_INTERVAL` configuration and validation.
- [ ] Run full tests; commit with `perf: throttle dynamic session discovery`.

### Task 4: Final verification

- [ ] Run all tests and compileall.
- [ ] Run `git diff --check`, inspect branch diff against master, and search for accidental secrets.
- [ ] Review all plan acceptance points and document remaining external-library risks.
