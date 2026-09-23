# Resource Reuse and Performance Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse GUI, contact mappings, and HTTP connections while persisting privacy-safe P50/P95 timings for the latest 50 samples per phase.

**Architecture:** Add one thread-safe `PerformanceTracker` that stores bounded in-memory samples and atomically writes one JSON snapshot per completed request. Existing service instances remain long-lived; `WeChatUISender` gains health-aware GUI reuse and a TTL/LRU contact cache, while DeepSeek, Firecrawl, and Open-Meteo expose explicit client lifecycle methods.

**Tech Stack:** Python 3.12, pytest/unittest, `collections.deque`/`OrderedDict`, atomic JSON files, OpenAI SDK, Firecrawl SDK, `httpx.Client`.

---

## File Structure

- Create `app/services/performance.py`: bounded samples, nearest-rank P50/P95, JSON loading and atomic persistence.
- Create `tests/test_performance.py`: tracker behavior, corruption handling, privacy and logging cadence.
- Modify `app/services/wechat_sender.py`: health-aware GUI reuse, TTL/LRU contact cache, UI timing hooks.
- Modify `tests/test_optimizations.py`: GUI rebuild and contact cache tests.
- Modify `app/ai/deepseek.py`: timing injection and `close()`.
- Modify `app/services/web_search.py`: timing injection and `close()`.
- Modify `app/services/weather.py`: persistent `httpx.Client` and `close()`.
- Modify `app/services/reference_context.py`: reference-context timing.
- Modify `app/services/bot_runtime.py`: routing/total timing and one flush per completed request.
- Modify `app/messages/reader.py`: message-read timing.
- Modify `app/main.py`: construct/inject tracker and close long-lived clients.
- Modify `.env.example` and `README.md`: performance file configuration and metric semantics.

### Task 1: Add the Rolling Performance Tracker

**Files:**
- Create: `app/services/performance.py`
- Create: `tests/test_performance.py`

- [ ] **Step 1: Write failing tracker tests**

```python
import json
import logging

from app.services.performance import PerformanceTracker


def test_tracker_keeps_latest_50_and_uses_nearest_rank(tmp_path):
    tracker = PerformanceTracker(tmp_path / "performance.json", window=50)
    for value in range(1, 61):
        tracker.record("total", float(value))
    tracker.complete_request()

    data = json.loads((tmp_path / "performance.json").read_text("utf-8"))
    assert data["phases"]["total"] == [float(v) for v in range(11, 61)]
    assert data["summary"]["total"] == {
        "count": 50,
        "p50": 35.0,
        "p95": 58.0,
    }


def test_tracker_loads_existing_samples_and_ignores_private_fields(tmp_path):
    path = tmp_path / "performance.json"
    path.write_text(json.dumps({
        "version": 1,
        "phases": {"ai_request": [1.0, -1, "bad", 2.0]},
        "user_id": "must-not-survive",
        "message": "must-not-survive",
    }), "utf-8")
    tracker = PerformanceTracker(path, window=50)
    tracker.complete_request()
    data = json.loads(path.read_text("utf-8"))
    assert data["phases"]["ai_request"] == [1.0, 2.0]
    assert "user_id" not in data and "message" not in data


def test_tracker_logs_summary_every_ten_completed_requests(tmp_path, caplog):
    tracker = PerformanceTracker(tmp_path / "performance.json", report_every=10)
    caplog.set_level(logging.INFO, logger="wx-bot")
    for _ in range(10):
        tracker.record("total", 1.0)
        tracker.complete_request()
    assert "性能汇总" in caplog.text
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_performance.py -q
```

Expected: FAIL because `app.services.performance` does not exist.

- [ ] **Step 3: Implement `PerformanceTracker`**

Implement the following public interface in `app/services/performance.py`:

```python
class PerformanceTracker:
    def __init__(self, path, window=50, report_every=10, clock=time.perf_counter): ...
    def record(self, phase: str, seconds: float) -> None: ...
    def complete_request(self) -> None: ...
    def summary(self) -> dict[str, dict[str, float | int]]: ...
    def flush(self) -> None: ...
```

Use `dict[str, deque[float]]`, `threading.RLock`, nearest-rank index `ceil(percentile * n) - 1`, and the same `mkstemp`/`fsync`/`os.replace` pattern already used by `JsonWatermarkStore`. Load only version `1`, phase names that are strings, and finite non-negative numeric samples. `record()` only mutates memory; `complete_request()` increments the request counter, calls `flush()`, and logs phase count/P50/P95 every tenth request. Persist only `version`, `updated_at`, `phases`, and computed `summary`.

- [ ] **Step 4: Run tracker tests and verify GREEN**

```powershell
python -m pytest tests/test_performance.py -q
```

Expected: all tracker tests PASS.

- [ ] **Step 5: Commit only tracker files**

```powershell
git add app/services/performance.py tests/test_performance.py
git commit --only -m "feat: persist rolling performance metrics" -- app/services/performance.py tests/test_performance.py
```

### Task 2: Reuse GUI and Contact Mappings Safely

**Files:**
- Modify: `app/services/wechat_sender.py`
- Modify: `tests/test_optimizations.py`

- [ ] **Step 1: Write failing GUI and contact-cache tests**

```python
def test_wechat_sender_rebuilds_only_dead_gui():
    class GUI:
        def __init__(self, alive): self.alive = alive
        def is_alive(self): return self.alive
    instances = [GUI(False), GUI(True)]
    sender = WeChatUISender(gui_factory=lambda: instances.pop(0))
    first = sender._get_gui()
    second = sender._get_gui()
    third = sender._get_gui()
    assert first is not second
    assert second is third


def test_contact_name_cache_uses_ttl_and_lru(monkeypatch):
    now = [0.0]
    calls = []
    sender = WeChatUISender(
        send_func=lambda *args: True,
        name_resolver=lambda user: calls.append(user) or f"name-{user}",
        name_cache_ttl=600,
        name_cache_size=2,
        clock=lambda: now[0],
    )
    assert sender._resolve_name("a") == "name-a"
    assert sender._resolve_name("a") == "name-a"
    now[0] = 601
    assert sender._resolve_name("a") == "name-a"
    assert calls == ["a", "a"]
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
python -m pytest tests/test_optimizations.py -q
```

Expected: FAIL because dead GUI instances are reused and cache constructor arguments are unsupported.

- [ ] **Step 3: Implement GUI health reuse and TTL/LRU cache**

In `WeChatUISender.__init__`, add optional `name_cache_ttl=600.0`, `name_cache_size=512`, and `clock=time.monotonic`. Store an `OrderedDict[str, tuple[float, str]]`. Reject non-positive cache settings.

Update `_get_gui()` under the existing `RLock`: return the cached instance when it has no `is_alive` method or `is_alive()` is true; otherwise clear and construct one replacement. Update `_resolve_name()` to evict expired entries, move cache hits to the end, cache only non-empty names different from the original ID, and pop the oldest item while over capacity.

- [ ] **Step 4: Run focused tests and verify GREEN**

```powershell
python -m pytest tests/test_optimizations.py tests/test_approval_queue.py -q
```

Expected: all focused tests PASS.

- [ ] **Step 5: Commit only sender/cache files**

```powershell
git add app/services/wechat_sender.py tests/test_optimizations.py
git commit --only -m "perf: reuse WeChat GUI and contact mappings" -- app/services/wechat_sender.py tests/test_optimizations.py
```

### Task 3: Reuse and Close HTTP Clients

**Files:**
- Modify: `requirements.txt`
- Modify: `app/ai/deepseek.py`
- Modify: `app/services/web_search.py`
- Modify: `app/services/weather.py`
- Modify: `tests/test_deepseek_client.py`
- Modify: `tests/test_web_search.py`
- Modify: `tests/test_weather.py`

- [ ] **Step 1: Write failing lifecycle tests**

Add these focused tests:

```python
def test_deepseek_close_delegates_to_sdk_client():
    class SDK:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())
            self.closed = 0
        def close(self): self.closed += 1
    sdk = SDK()
    client = DeepSeekClient(DeepSeekConfig(api_key="test"), sdk_client=sdk)
    client.close()
    assert sdk.closed == 1


def test_firecrawl_close_delegates_to_sdk_client():
    class SDK:
        def __init__(self): self.closed = 0
        def close(self): self.closed += 1
    sdk = SDK()
    client = FirecrawlSearchClient(client=sdk)
    client.close()
    assert sdk.closed == 1
```

Add the following weather test:

```python
def test_weather_reuses_injected_http_client_and_closes_it():
    class Client:
        def __init__(self): self.calls = []; self.closed = 0
        def get(self, url, params, headers, timeout):
            self.calls.append(url)
            payload = ({"results": [{"name": "宁波", "latitude": 1, "longitude": 2}]}
                       if "geocoding" in url else
                       {"current": {"temperature_2m": 1, "apparent_temperature": 2,
                        "relative_humidity_2m": 3, "weather_code": 0,
                        "wind_speed_10m": 4}})
            return type("Response", (), {
                "raise_for_status": lambda self: None,
                "json": lambda self: payload,
            })()
        def close(self): self.closed += 1
    raw = Client()
    client = OpenMeteoWeatherClient(http_client=raw)
    client.get_current("宁波")
    assert len(raw.calls) == 2
    client.close()
    assert raw.closed == 1
```

- [ ] **Step 2: Run lifecycle tests and verify RED**

```powershell
python -m pytest tests/test_deepseek_client.py tests/test_web_search.py tests/test_weather.py -q
```

Expected: FAIL because close methods and weather `http_client` injection do not exist.

- [ ] **Step 3: Implement lifecycle methods**

Add `httpx>=0.27.0` to `requirements.txt`. `OpenMeteoWeatherClient` accepts either legacy `http_get` or `http_client`; when neither is supplied it creates one `httpx.Client` with the user-agent and 10-second timeout. Its internal request uses `client.get(...).raise_for_status().json()`. `close()` calls the client's optional close method exactly once. DeepSeek and Firecrawl `close()` similarly call optional SDK close methods and tolerate absence.

- [ ] **Step 4: Run lifecycle tests and verify GREEN**

```powershell
python -m pytest tests/test_deepseek_client.py tests/test_web_search.py tests/test_weather.py -q
```

Expected: all lifecycle tests PASS.

- [ ] **Step 5: Commit only HTTP lifecycle files**

```powershell
git add requirements.txt app/ai/deepseek.py app/services/web_search.py app/services/weather.py tests/test_deepseek_client.py tests/test_web_search.py tests/test_weather.py
git commit --only -m "perf: reuse outbound HTTP clients" -- requirements.txt app/ai/deepseek.py app/services/web_search.py app/services/weather.py tests/test_deepseek_client.py tests/test_web_search.py tests/test_weather.py
```

### Task 4: Instrument Phases and Flush Once per Request

**Files:**
- Modify: `app/ai/deepseek.py`
- Modify: `app/services/web_search.py`
- Modify: `app/services/reference_context.py`
- Modify: `app/services/wechat_sender.py`
- Modify: `app/messages/reader.py`
- Modify: `app/services/bot_runtime.py`
- Modify: `tests/test_performance.py`
- Modify: `tests/test_bot_runtime.py`

- [ ] **Step 1: Write failing instrumentation tests**

Use this fake tracker in focused service tests:

```python
class FakePerformance:
    def __init__(self):
        self.records = []
        self.completed = 0
    def record(self, phase, seconds):
        self.records.append((phase, seconds))
    def complete_request(self):
        self.completed += 1
```

Verify DeepSeek and Firecrawl record their phases:

```python
def test_deepseek_records_ai_request_phase():
    perf = FakePerformance()
    completions = FakeCompletions(SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    ))
    client = DeepSeekClient(
        DeepSeekConfig(api_key="test"),
        sdk_client=FakeSDKClient(completions),
        performance=perf,
    )
    client.complete([{"role": "user", "content": "hello"}])
    assert [name for name, _ in perf.records] == ["ai_request"]
```

Verify the runtime completes exactly one request for every return path:

```python
def test_runtime_records_total_and_completes_metrics_once():
    perf = FakePerformance()
    runtime = BotRuntime(
        reply_service=FakeAI("answer"),
        approval_queue=FakeQueue(),
        performance=perf,
    )
    runtime.handle_event(MessageEvent("alice", {"type": "文本", "content": "hi"}))
    assert perf.completed == 1
    assert [name for name, _ in perf.records].count("total") == 1
    assert [name for name, _ in perf.records].count("routing") == 1
```

- [ ] **Step 2: Run instrumentation tests and verify RED**

```powershell
python -m pytest tests/test_performance.py tests/test_bot_runtime.py tests/test_deepseek_client.py tests/test_web_search.py -q
```

Expected: FAIL because services do not accept a tracker.

- [ ] **Step 3: Add optional tracker injection**

Add `performance=None` to constructors without changing existing call sites. Record durations in `finally` blocks for `ai_request`, `web_search`, `reference_context`, `message_read`, `routing`, `contact_resolve`, `ui_open_chat`, `ui_send`, and `send_verify`. Refactor `BotRuntime.handle_event()` into a thin timing wrapper around `_handle_event()` so every return path records `total` and calls `complete_request()` once. `_handle_event()` records `routing` immediately before entering reply generation or returning a command/ignored result. Tracker exceptions must be caught and logged by the tracker itself, never by business services.

- [ ] **Step 4: Run instrumentation tests and verify GREEN**

```powershell
python -m pytest tests/test_performance.py tests/test_bot_runtime.py tests/test_deepseek_client.py tests/test_web_search.py tests/test_approval_queue.py -q
```

Expected: all instrumentation tests PASS.

- [ ] **Step 5: Commit only instrumentation files**

```powershell
git add app/ai/deepseek.py app/services/web_search.py app/services/reference_context.py app/services/wechat_sender.py app/messages/reader.py app/services/bot_runtime.py tests/test_performance.py tests/test_bot_runtime.py tests/test_deepseek_client.py tests/test_web_search.py
git commit --only -m "feat: record phased reply latency" -- app/ai/deepseek.py app/services/web_search.py app/services/reference_context.py app/services/wechat_sender.py app/messages/reader.py app/services/bot_runtime.py tests/test_performance.py tests/test_bot_runtime.py tests/test_deepseek_client.py tests/test_web_search.py
```

### Task 5: Wire Configuration, Shutdown, and Documentation

**Files:**
- Modify: `app/main.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing main wiring test**

Test that `build_runtime(..., performance=tracker)` passes the same tracker to reader, sender, and runtime. Add this shutdown test:

```python
def test_close_services_closes_each_unique_service_once():
    class Service:
        def __init__(self): self.closed = 0
        def close(self): self.closed += 1
    first = Service()
    second = Service()
    close_services(first, first, second, object())
    assert first.closed == 1
    assert second.closed == 1
```

- [ ] **Step 2: Run main tests and verify RED**

```powershell
python -m pytest tests/test_main.py -q
```

Expected: FAIL because performance injection and shutdown helper do not exist.

- [ ] **Step 3: Wire the tracker and shutdown**

Create the tracker in `main()` using:

```python
performance_path = os.getenv(
    "WX_BOT_PERFORMANCE_FILE",
    str(_default_watermark_path().with_name("performance.json")),
)
performance = PerformanceTracker(performance_path, window=50, report_every=10)
```

Pass it to DeepSeek, weather/search where applicable, reply/reference services, reader, sender, and runtime. Keep concrete client variables instead of constructing weather/search inline. In `finally`, stop scheduler/listener first, flush performance, then call `close_services(ai_client, search_client, weather_client)`. Document `WX_BOT_PERFORMANCE_FILE`, the 50-sample window, phase names, and privacy behavior in README and `.env.example`.

- [ ] **Step 4: Run focused and full verification**

```powershell
python -m pytest tests/test_main.py tests/test_performance.py tests/test_optimizations.py tests/test_weather.py tests/test_web_search.py tests/test_deepseek_client.py -q
python -m pytest -q
& 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' -m compileall -q app
git diff --check
```

Expected: focused tests PASS. Full-suite output must introduce no failures beyond the two pre-existing `tests/test_style_reply.py` interface failures documented before this plan. Python 3.12 compile and whitespace checks exit 0.

- [ ] **Step 5: Commit only wiring/documentation files**

```powershell
git add app/main.py .env.example README.md tests/test_main.py
git commit --only -m "feat: wire persistent performance tracking" -- app/main.py .env.example README.md tests/test_main.py
```
