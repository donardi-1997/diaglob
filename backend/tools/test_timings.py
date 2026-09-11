from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


class TimingCollector:
    def __init__(self) -> None:
        self._durations: dict[str, float] = defaultdict(float)

    def record(self, nodeid: str, duration: float) -> None:
        test_path = nodeid.split("::", 1)[0].replace("\\", "/")
        if not test_path.startswith("tests/") or not test_path.endswith(".py"):
            return
        self._durations[test_path] += max(float(duration), 0.0)

    def snapshot(self) -> dict[str, float]:
        return {
            path: round(duration, 6)
            for path, duration in sorted(self._durations.items())
        }

    def write(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


_collector = TimingCollector()
_output: Path | None = None


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--timings-output",
        action="store",
        default=None,
        help="Write cumulative pytest durations by test file to JSON.",
    )


def pytest_configure(config) -> None:
    global _collector, _output
    _collector = TimingCollector()
    output = config.getoption("timings_output")
    _output = Path(output) if output else None


def pytest_runtest_logreport(report) -> None:
    if _output is None:
        return
    _collector.record(report.nodeid, report.duration)


def pytest_sessionfinish(session, exitstatus) -> None:
    del session, exitstatus
    if _output is not None:
        _collector.write(_output)
