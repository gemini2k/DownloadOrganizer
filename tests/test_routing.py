from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from download_organizer import safety
from download_organizer.organizer import (
    DUPLICATES_DIR,
    OLD_FILES_DIR,
    build_move_plan,
    organized_dir_names,
)


@pytest.fixture
def downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    d.mkdir()
    (d / "fresh.pdf").write_bytes(b"fresh")
    (d / "dup1.txt").write_bytes(b"same")
    (d / "dup2.txt").write_bytes(b"same")  # duplicate of dup1
    old = d / "ancient.pdf"
    old.write_bytes(b"old")
    ts = time.time() - 400 * 86400  # ~400 days ago
    os.utime(old, (ts, ts))
    return d


def _dst_for(plan, name: str) -> Path:
    return next(Path(p.dst) for p in plan if Path(p.src).name == name)


def test_route_old_sends_old_to_bucket(downloads: Path, tmp_path: Path):
    plan = build_move_plan(downloads, tmp_path / "out", old_days=180, route_old=True)["plan"]
    assert OLD_FILES_DIR in _dst_for(plan, "ancient.pdf").parts
    assert OLD_FILES_DIR not in _dst_for(plan, "fresh.pdf").parts  # fresh stays in category


def test_route_duplicates_sends_dups_to_bucket(downloads: Path, tmp_path: Path):
    plan = build_move_plan(downloads, tmp_path / "out", old_days=180, route_duplicates=True)["plan"]
    assert DUPLICATES_DIR in _dst_for(plan, "dup1.txt").parts
    assert DUPLICATES_DIR in _dst_for(plan, "dup2.txt").parts
    # collision-safe naming keeps both copies
    assert _dst_for(plan, "dup1.txt") != _dst_for(plan, "dup2.txt")


def test_routing_default_off(downloads: Path, tmp_path: Path):
    plan = build_move_plan(downloads, tmp_path / "out", old_days=180)["plan"]
    assert OLD_FILES_DIR not in _dst_for(plan, "ancient.pdf").parts
    assert DUPLICATES_DIR not in _dst_for(plan, "dup1.txt").parts


def test_review_buckets_excluded_from_recursive_scan():
    # the bucket folder names must be in the auto-exclude set so a recursive rescan
    # never picks routed files back up
    assert OLD_FILES_DIR in organized_dir_names()
    assert DUPLICATES_DIR in organized_dir_names()
