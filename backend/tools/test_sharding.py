from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

WeightedFile = tuple[str, int]


def assign_shards(weighted_files: Sequence[WeightedFile], shard_count: int) -> list[list[str]]:
    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")

    shards: list[list[str]] = [[] for _ in range(shard_count)]
    totals = [0 for _ in range(shard_count)]

    for path, weight in sorted(weighted_files, key=lambda item: (-item[1], item[0])):
        shard_index = min(range(shard_count), key=lambda index: (totals[index], index))
        shards[shard_index].append(path)
        totals[shard_index] += max(weight, 0)

    return shards


def discover_test_files(root: Path = Path("tests")) -> list[WeightedFile]:
    return [
        (path.as_posix(), path.stat().st_size)
        for path in sorted(root.rglob("test_*.py"))
        if path.is_file()
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select one deterministic pytest file shard.")
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shards = assign_shards(discover_test_files(), args.count)

    if args.index < 0 or args.index >= args.count:
        raise SystemExit(f"shard index must be between 0 and {args.count - 1}")

    for path in shards[args.index]:
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
