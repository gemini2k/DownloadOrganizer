from __future__ import annotations

from pathlib import Path

import pytest

from download_organizer import safety
from download_organizer.analyzer import analyze_files
from download_organizer.organizer import build_move_plan


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    (d / "sub").mkdir(parents=True)
    (d / "문서").mkdir()  # looks like our organized output (category folder)
    (d / "top.pdf").write_bytes(b"top")
    (d / "sub" / "nested.pdf").write_bytes(b"nested")
    (d / "문서" / "already.pdf").write_bytes(b"organized")
    return d


def test_default_is_top_level_only(tree: Path):
    names = {r.path.name for r in analyze_files(tree, old_days=180)}
    assert names == {"top.pdf"}  # subfolders not entered


def test_recursive_includes_subfolders(tree: Path):
    names = {
        r.path.name
        for r in analyze_files(tree, old_days=180, recursive=True, exclude_dirs=["문서"])
    }
    assert names == {"top.pdf", "nested.pdf"}  # '문서' (organized) excluded


def test_recursive_user_exclude_dir(tree: Path):
    names = {
        r.path.name
        for r in analyze_files(tree, old_days=180, recursive=True, exclude_dirs=["문서", "sub"])
    }
    assert names == {"top.pdf"}


def test_build_move_plan_auto_excludes_organized_dirs(tree: Path, tmp_path: Path):
    # build_move_plan should auto-exclude the '문서' organized folder in recursive mode.
    context = build_move_plan(tree, tmp_path / "out", old_days=180, recursive=True)
    srcs = {Path(p.src).name for p in context["plan"]}
    assert "already.pdf" not in srcs
    assert {"top.pdf", "nested.pdf"} <= srcs


def test_in_plan_basename_collision_gets_unique_dst(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    (d / "a").mkdir(parents=True)
    (d / "b").mkdir()
    (d / "a" / "report.pdf").write_bytes(b"one")
    (d / "b" / "report.pdf").write_bytes(b"two")  # same basename, different folder

    context = build_move_plan(d, tmp_path / "out", old_days=180, recursive=True)
    dsts = [Path(p.dst) for p in context["plan"]]
    assert len(dsts) == 2
    assert len(set(dsts)) == 2  # must not collide into the same destination
