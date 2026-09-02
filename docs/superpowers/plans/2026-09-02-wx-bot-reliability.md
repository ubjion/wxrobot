# WeChat Bot Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent live message loss, stop malformed commands from retrying forever, and make scheduled-message state thread-safe and timezone-consistent.

**Architecture:** Message polling returns ordered events without treating an entire poll batch as acknowledged; the listener advances and persists a per-user cursor only after each successful callback. Command parsing errors become handled replies. Scheduler state uses a lock and snapshots due work before performing slow sends.

**Tech Stack:** Python 3.13, standard-library threading/datetime, pytest.

---

### Task 1: Acknowledge messages only after successful handling

**Files:**
- Modify: `app/messages/reader.py`
- Modify: `tests/test_message_reader.py`

- [ ] Add a failing test where two users each have one event, the first callback raises, and the second user's watermark remains unadvanced so its message is delivered on the next cycle.
- [ ] Add a failing test showing `MessageReader.ack(event)` advances only the matching user's watermark and removes older seen identities for that user.
- [ ] Run `C:\Python313\python.exe -m pytest tests/test_message_reader.py -q`; verify failures demonstrate premature batch acknowledgement.
- [ ] Change `poll_once()` to use local per-user scan positions while leaving persisted `watermarks` unchanged. Add `ack(event)` that advances the user watermark to the event `sort_seq`; acknowledge duplicate/filtered records through the local scan position so polling terminates without replay loops.
- [ ] Change `MessageListener._run()` to call `reader.ack(event)` and persist after each successful callback. On failure, leave the failed and later events unacknowledged and break.
- [ ] Bound `_seen` by pruning acknowledged identities for that user.
- [ ] Run focused tests and full `C:\Python313\python.exe -m pytest -q`.
- [ ] Commit with `fix: acknowledge messages after successful handling`.

### Task 2: Handle malformed schedule commands once

**Files:**
- Modify: `app/services/bot_runtime.py`
- Modify: `tests/test_schedule_commands.py`

- [ ] Add failing tests for `/每 abc 你好`, `/每 -1 你好`, and malformed `/定时` values. Each must enqueue one format-error reply instead of raising.
- [ ] Run `C:\Python313\python.exe -m pytest tests/test_schedule_commands.py -q`; verify RED.
- [ ] Wrap `parse_schedule_command(content)` in `try/except (ValueError, TypeError, OverflowError)` inside `handle_event()`. Return the existing format-error reply through `_enqueue_or_send`.
- [ ] Keep non-command messages and valid commands unchanged.
- [ ] Run focused and full tests.
- [ ] Commit with `fix: handle malformed schedule commands`.

### Task 3: Make scheduler state thread-safe

**Files:**
- Modify: `app/services/scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] Add a failing concurrency test that blocks a due send while another thread adds a task; after the send finishes, both the recurring/remaining state and newly added task must exist.
- [ ] Add a failing test that concurrent cancellation during a blocked send is not overwritten when `run_once()` saves its snapshot.
- [ ] Run `C:\Python313\python.exe -m pytest tests/test_scheduler.py -q`; verify RED.
- [ ] Add `threading.RLock`. Protect list/add/cancel and state replacement. In `run_once()`, claim a snapshot under the lock, perform sends without holding the lock, then merge results by schedule ID so additions and cancellations made during sends are preserved.
- [ ] Persist only while holding the lock, but write from a copied list.
- [ ] Run focused and full tests.
- [ ] Commit with `fix: synchronize scheduled message state`.

### Task 4: Normalize naive schedule times to local timezone

**Files:**
- Modify: `app/services/scheduler.py`
- Modify: `tests/test_scheduler.py`
- Modify: `README.md`

- [ ] Add a failing test that a naive ISO value is interpreted in the configured local timezone and stored/compared as an aware instant.
- [ ] Run the focused test and verify RED.
- [ ] Replace the UTC assumption with a scheduler `local_timezone` dependency defaulting to `datetime.now().astimezone().tzinfo`. Normalize naive input with that timezone and convert comparisons to UTC.
- [ ] Document that timezone-less console timestamps use the machine timezone.
- [ ] Run focused and full tests.
- [ ] Commit with `fix: normalize schedule timezones`.

### Task 5: Reliability verification

**Files:**
- No production changes unless a new failing regression test first demonstrates a defect.

- [ ] Run `C:\Python313\python.exe -m pytest -q` and require zero failures.
- [ ] Run `C:\Python313\python.exe -m compileall -q app tests`.
- [ ] Run `git diff --check`.
- [ ] Inspect `git status --short` and verify only planned files/plan commits exist.
