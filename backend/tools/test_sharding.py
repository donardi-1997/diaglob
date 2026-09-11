from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence

WeightedFile = tuple[str, float]


def assign_shards(weighted_files: Sequence[WeightedFile], shard_count: int) -> list[list[str]]:
    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")

    shards: list[list[str]] = [[] for _ in range(shard_count)]
    totals = [0.0 for _ in range(shard_count)]

    for path, weight in sorted(weighted_files, key=lambda item: (-item[1], item[0])):
        shard_index = min(range(shard_count), key=lambda index: (totals[index], index))
        shards[shard_index].append(path)
        totals[shard_index] += max(weight, 0.0)

    return shards


def _repo_test_path(root: Path, path: Path) -> str:
    return (Path(root.name) / path.relative_to(root)).as_posix()


def discover_test_files(
    root: Path = Path("tests"),
    *,
    timings: Mapping[str, float] | None = None,
) -> list[WeightedFile]:
    files = [path for path in sorted(root.rglob("test_*.py")) if path.is_file()]
    timing_map = timings or {}

    seconds_per_byte = [
        timing_map[_repo_test_path(root, path)] / path.stat().st_size
        for path in files
        if _repo_test_path(root, path) in timing_map and path.stat().st_size > 0
    ]
    fallback_scale = median(seconds_per_byte) if seconds_per_byte else 1.0

    return [
        (
            _repo_test_path(root, path),
            timing_map.get(_repo_test_path(root, path), path.stat().st_size * fallback_scale),
        )
        for path in files
    ]


def load_timings(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("timings file must contain a JSON object")

    return {str(test_path): float(duration) for test_path, duration in raw.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select one deterministic pytest file shard.")
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--timings", type=Path, default=Path("test_timings.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timings = load_timings(args.timings)
    shards = assign_shards(discover_test_files(timings=timings), args.count)

    if args.index < 0 or args.index >= args.count:
        raise SystemExit(f"shard index must be between 0 and {args.count - 1}")

    for path in shards[args.index]:
        print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
