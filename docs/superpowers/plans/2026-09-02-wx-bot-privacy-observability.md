# WeChat Bot Privacy and Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent common sensitive values and real group identities from being persisted or sent to the model, add user-controlled context deletion, and make failures diagnosable without logging message bodies.

**Architecture:** A deterministic text redactor is injected into context persistence. Group summaries assign per-summary anonymous member labels. Runtime and reader logs contain event routes, anonymous session fingerprints, latency, and exception classes, never message content.

**Tech Stack:** Python 3.13 standard library, logging, hashlib, regex, pytest.

---

### Task 1: Redact persisted context

**Files:**
- Create: `app/services/privacy.py`
- Modify: `app/services/context_store.py`
- Create: `tests/test_privacy.py`
- Modify: `tests/test_context_store.py`

- [ ] Add failing tests for phone, email, ID card, `wxid_*`, Bearer token, `api_key`, and password assignment redaction while preserving ordinary Chinese text.
- [ ] Add a failing context-store test proving both user and assistant text are redacted before JSON persistence.
- [ ] Run focused tests and verify RED.
- [ ] Implement `redact_sensitive_text(text)` and `anonymous_id(value)` in `privacy.py`. Use placeholders `[PHONE]`, `[EMAIL]`, `[ID_CARD]`, `[USER]`, and `[SECRET]`.
- [ ] Add an optional redactor dependency to `JsonContextStore`, defaulting to `redact_sensitive_text`, and apply it only when saving new exchanges.
- [ ] Run focused and full tests; commit with `feat: redact persisted conversation context`.

### Task 2: Add context deletion command

**Files:**
- Modify: `app/services/reply_service.py`
- Modify: `app/services/bot_runtime.py`
- Modify: `tests/test_context_store.py`
- Modify: `README.md`

- [ ] Add a failing runtime test for `/清除上下文`; it must clear only the sender's context, enqueue a confirmation, and not call AI.
- [ ] Add `AiReplyService.clear_context(user_id) -> bool`, returning false if no store is configured.
- [ ] Route the exact command before scheduling/weather/search logic.
- [ ] Document the command; run tests and commit with `feat: add context deletion command`.

### Task 3: Pseudonymize group summaries

**Files:**
- Modify: `app/services/group_summary.py`
- Modify: `tests/test_group_summary.py`

- [ ] Replace the existing display-name expectation with a failing test requiring stable labels `成员1`, `成员2` within one summary and no `wxid` or resolved nickname in the model prompt.
- [ ] Run focused tests and verify RED.
- [ ] Build a local mapping per `summarize()` call from sender identity to sequential labels; strip sender prefixes from message text and use labels in both message lines and counts.
- [ ] Run focused/full tests; commit with `feat: pseudonymize group summary participants`.

### Task 4: Add privacy-safe operational logging

**Files:**
- Modify: `app/messages/reader.py`
- Modify: `app/services/bot_runtime.py`
- Modify: `app/services/reply_service.py`
- Modify: `tests/test_message_reader.py`
- Modify: `tests/test_bot_runtime.py`

- [ ] Add failing `caplog` tests proving callback and AI failures log exception class plus anonymous session fingerprint, while excluding raw user ID and message body.
- [ ] Add module loggers. Log database read/discovery failures, callback failures, selected reply route, fallback use, and elapsed seconds.
- [ ] Use `anonymous_id(event.user)` for session correlation. Do not log `content`, generated reply, nicknames, keys, or URLs.
- [ ] Run focused/full tests; commit with `feat: add privacy-safe runtime diagnostics`.

### Task 5: Verify privacy stage

- [ ] Run `C:\Python313\python.exe -m pytest -q`.
- [ ] Run `C:\Python313\python.exe -m compileall -q app tests`.
- [ ] Run `git diff --check`.
- [ ] Search tracked application/docs for realistic secret patterns and verify matches occur only in redaction tests.
