"""Benchmark: fast vs strict duplicate detection.

Generates synthetic files in a temporary folder (never touches your real Downloads),
runs `duplicate_groups` in both modes, and prints a timing + result comparison.

Usage:
    python benchmarks/bench_dup_mode.py
    python benchmarks/bench_dup_mode.py --count 40 --size-mb 20 --repeats 3

Scenario: `count` files that all share the same size and an identical first 1 MB,
but differ afterwards. This is the case that separates the two modes:
- strict reads every byte  -> reports 0 duplicates (correct)
- fast reads only 1 MB     -> reports all as one group (over-report), much less I/O
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "src").resolve()))

from download_organizer.analyzer import analyze_files, duplicate_groups


def make_dataset(root: Path, count: int, size_mb: int) -> None:
    head = b"X" * (1024 * 1024)  # identical first 1 MB across all files
    tail_len = max(0, size_mb - 1) * 1024 * 1024
    for i in range(count):
        # same total size for every file, but a distinct first tail byte -> distinct content
        tail = bytes([i % 251]) * tail_len if tail_len else bytes([i % 251])
        (root / f"file_{i:03d}.bin").write_bytes(head + tail)


def time_mode(records, mode: str, repeats: int) -> tuple[float, int]:
    best = float("inf")
    groups = []
    for _ in range(repeats):
        start = time.perf_counter()
        groups = duplicate_groups(records, mode=mode)
        best = min(best, time.perf_counter() - start)
    return best, sum(len(g) for g in groups)


def main() -> int:
    parser = argparse.ArgumentParser(description="fast vs strict duplicate detection benchmark")
    parser.add_argument("--count", type=int, default=30, help="number of same-size files")
    parser.add_argument("--size-mb", type=int, default=20, help="size of each file in MB")
    parser.add_argument("--repeats", type=int, default=3, help="timed repeats (best is reported)")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="do_bench_"))
    try:
        print(f"Generating {args.count} files x {args.size_mb} MB in {tmp} ...")
        make_dataset(tmp, args.count, args.size_mb)
        records = analyze_files(tmp, old_days=180)
        total_mb = sum(r.size for r in records) / (1024 * 1024)

        fast_t, fast_flagged = time_mode(records, "fast", args.repeats)
        strict_t, strict_flagged = time_mode(records, "strict", args.repeats)

        speedup = strict_t / fast_t if fast_t else float("inf")
        print()
        print(f"dataset: {args.count} files, {total_mb:.0f} MB total, identical first 1 MB")
        print(f"{'mode':<8}{'time (s)':<12}{'files flagged as dup':<22}")
        print(f"{'fast':<8}{fast_t:<12.4f}{fast_flagged:<22}")
        print(f"{'strict':<8}{strict_t:<12.4f}{strict_flagged:<22}")
        print()
        print(f"strict / fast time ratio: {speedup:.1f}x")
        print(f"fast flagged {fast_flagged} files as duplicates (over-report); "
              f"strict flagged {strict_flagged} (exact).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
