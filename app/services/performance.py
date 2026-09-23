"""Privacy-safe rolling performance metrics."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any


logger = logging.getLogger("wx-bot")


class PerformanceTracker:
    """Keep bounded phase timings and persist an atomic JSON snapshot."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        window: int = 50,
        report_every: int = 10,
        clock: Any = time.perf_counter,
    ) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        if report_every <= 0:
            raise ValueError("report_every must be positive")
        self.path = Path(path)
        self.window = window
        self.report_every = report_every
        self.clock = clock
        self._lock = threading.RLock()
        self._samples: dict[str, deque[float]] = {}
        self._completed = 0
        self._load()

    def record(self, phase: str, seconds: float) -> None:
        if not isinstance(phase, str) or not phase.strip():
            return
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            return
        value = float(seconds)
        if value < 0 or not math.isfinite(value):
            return
        with self._lock:
            samples = self._samples.setdefault(
                phase.strip(), deque(maxlen=self.window)
            )
            samples.append(value)

    def complete_request(self) -> None:
        with self._lock:
            self._completed += 1
            should_report = self._completed % self.report_every == 0
        self.flush()
        if should_report:
            logger.info(
                "性能汇总（最近%d次） %s",
                self.window,
                json.dumps(self.summary(), ensure_ascii=False, sort_keys=True),
            )

    def summary(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            return {
                phase: self._phase_summary(list(samples))
                for phase, samples in sorted(self._samples.items())
                if samples
            }

    def flush(self) -> None:
        try:
            with self._lock:
                phases = {
                    phase: list(samples)
                    for phase, samples in sorted(self._samples.items())
                    if samples
                }
                payload = {
                    "version": 1,
                    "updated_at": datetime.now().astimezone().isoformat(),
                    "phases": phases,
                    "summary": {
                        phase: self._phase_summary(values)
                        for phase, values in phases.items()
                    },
                }
            self._atomic_write(payload)
        except Exception as exc:
            logger.warning("性能统计写入失败 error=%s", type(exc).__name__)

    @staticmethod
    def _phase_summary(values: list[float]) -> dict[str, float | int]:
        ordered = sorted(values)
        return {
            "count": len(ordered),
            "p50": ordered[math.ceil(0.50 * len(ordered)) - 1],
            "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
        }

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception as exc:
            logger.warning("性能统计读取失败 error=%s", type(exc).__name__)
            return
        if not isinstance(data, dict) or data.get("version") != 1:
            return
        phases = data.get("phases")
        if not isinstance(phases, dict):
            return
        for phase, raw_values in phases.items():
            if not isinstance(phase, str) or not isinstance(raw_values, list):
                continue
            values = deque(maxlen=self.window)
            for raw in raw_values:
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    continue
                value = float(raw)
                if value >= 0 and math.isfinite(value):
                    values.append(value)
            if values:
                self._samples[phase] = values

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp:
                json.dump(payload, temp, ensure_ascii=False, indent=2)
                temp.write("\n")
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
