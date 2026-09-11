from pathlib import Path

from tools.test_sharding import assign_shards, discover_test_files


def test_assign_shards_covers_each_file_exactly_once():
    weighted_files = [
        ("tests/test_a.py", 100),
        ("tests/test_b.py", 80),
        ("tests/test_c.py", 40),
        ("tests/test_d.py", 20),
    ]

    shards = assign_shards(weighted_files, shard_count=2)

    assigned = [path for shard in shards for path in shard]
    assert sorted(assigned) == sorted(path for path, _ in weighted_files)
    assert len(assigned) == len(set(assigned))


def test_assign_shards_balances_largest_files_greedily():
    weighted_files = [
        ("tests/test_a.py", 100),
        ("tests/test_b.py", 90),
        ("tests/test_c.py", 20),
        ("tests/test_d.py", 10),
    ]

    shards = assign_shards(weighted_files, shard_count=2)

    assert shards == [
        ["tests/test_a.py", "tests/test_d.py"],
        ["tests/test_b.py", "tests/test_c.py"],
    ]


def test_assign_shards_rejects_invalid_shard_count():
    try:
        assign_shards([("tests/test_a.py", 1)], shard_count=0)
    except ValueError as exc:
        assert str(exc) == "shard_count must be at least 1"
    else:
        raise AssertionError("expected ValueError")


def test_discover_test_files_prefers_historical_timings(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    slow = tests_dir / "test_slow.py"
    fast = tests_dir / "test_fast.py"
    slow.write_text("def test_slow():\n    pass\n", encoding="utf-8")
    fast.write_text("def test_fast():\n    pass\n", encoding="utf-8")

    timings = {
        "tests/test_slow.py": 12.5,
        "tests/test_fast.py": 0.75,
    }

    weighted = discover_test_files(tests_dir, timings=timings)

    assert dict(weighted)["tests/test_slow.py"] == 12.5
    assert dict(weighted)["tests/test_fast.py"] == 0.75


def test_discover_test_files_falls_back_for_new_tests(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    known = tests_dir / "test_known.py"
    new = tests_dir / "test_new.py"
    known.write_text("def test_known():\n    pass\n", encoding="utf-8")
    new.write_text("def test_new():\n    pass\n" * 5, encoding="utf-8")

    weighted = discover_test_files(tests_dir, timings={"tests/test_known.py": 2.0})
    weights = dict(weighted)

    assert weights["tests/test_known.py"] == 2.0
    assert weights["tests/test_new.py"] > 0
