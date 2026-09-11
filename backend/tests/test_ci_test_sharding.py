from tools.test_sharding import assign_shards


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
