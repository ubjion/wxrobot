import json
import logging

from app.services.performance import PerformanceTracker


def test_tracker_keeps_latest_50_and_uses_nearest_rank(tmp_path):
    tracker = PerformanceTracker(tmp_path / "performance.json", window=50)
    for value in range(1, 61):
        tracker.record("total", float(value))

    tracker.complete_request()

    data = json.loads((tmp_path / "performance.json").read_text("utf-8"))
    assert data["phases"]["total"] == [float(value) for value in range(11, 61)]
    assert data["summary"]["total"] == {
        "count": 50,
        "p50": 35.0,
        "p95": 58.0,
    }


def test_tracker_loads_existing_samples_and_drops_private_fields(tmp_path):
    path = tmp_path / "performance.json"
    path.write_text(
        json.dumps({
            "version": 1,
            "phases": {"ai_request": [1.0, -1, "bad", 2.0]},
            "user_id": "must-not-survive",
            "message": "must-not-survive",
        }),
        "utf-8",
    )

    tracker = PerformanceTracker(path, window=50)
    tracker.complete_request()

    data = json.loads(path.read_text("utf-8"))
    assert data["phases"]["ai_request"] == [1.0, 2.0]
    assert "user_id" not in data
    assert "message" not in data


def test_tracker_logs_summary_every_ten_completed_requests(tmp_path, caplog):
    tracker = PerformanceTracker(tmp_path / "performance.json", report_every=10)
    caplog.set_level(logging.INFO, logger="wx-bot")

    for _ in range(10):
        tracker.record("total", 1.0)
        tracker.complete_request()

    assert "性能汇总" in caplog.text


def test_tracker_ignores_corrupt_file_and_writes_valid_snapshot(tmp_path):
    path = tmp_path / "performance.json"
    path.write_text("not-json", "utf-8")

    tracker = PerformanceTracker(path)
    tracker.record("total", 1.25)
    tracker.complete_request()

    data = json.loads(path.read_text("utf-8"))
    assert data["phases"]["total"] == [1.25]
