from pathlib import Path

from tools.test_timings import TimingCollector


def test_timing_collector_aggregates_all_phases_by_file(tmp_path: Path):
    collector = TimingCollector()

    collector.record("tests/test_orders.py::test_create", 0.4)
    collector.record("tests/test_orders.py::test_create", 0.8)
    collector.record("tests/test_orders.py::test_create", 0.2)
    collector.record("tests/test_auth.py::test_login", 0.5)

    assert collector.snapshot() == {
        "tests/test_auth.py": 0.5,
        "tests/test_orders.py": 1.4,
    }

    output = tmp_path / "timings.json"
    collector.write(output)

    assert output.read_text(encoding="utf-8") == (
        '{\n'
        '  "tests/test_auth.py": 0.5,\n'
        '  "tests/test_orders.py": 1.4\n'
        '}\n'
    )


def test_timing_collector_ignores_non_test_nodeids():
    collector = TimingCollector()

    collector.record("", 1.0)
    collector.record("<unknown>", 2.0)

    assert collector.snapshot() == {}
