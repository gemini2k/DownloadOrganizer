from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

import pytest

from download_organizer import cleaner, safety
from download_organizer.cleaner import build_clean_plan, compute_clean_token, execute_clean, trash_empty_dirs
from download_organizer.service import ConfirmationError, run_clean


@pytest.fixture
def downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    d.mkdir()
    (d / "keep.pdf").write_bytes(b"unique")
    (d / "dup1.txt").write_bytes(b"same-content")
    (d / "dup2.txt").write_bytes(b"same-content")
    (d / "dup3.txt").write_bytes(b"same-content")
    old = d / "ancient.png"
    old.write_bytes(b"img")
    ts = time.time() - 400 * 86400
    os.utime(old, (ts, ts))
    return d


@pytest.fixture
def fake_trash(monkeypatch: pytest.MonkeyPatch):
    """Capture trashed paths instead of touching the real Recycle Bin."""
    trashed: list[str] = []
    fake = types.ModuleType("send2trash")
    fake.send2trash = lambda p: trashed.append(str(p))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "send2trash", fake)
    return trashed


def test_duplicates_keep_one_per_group(downloads: Path):
    items = build_clean_plan(downloads, old_days=180, trash_duplicates=True)
    dup = [i for i in items if i.reason == "duplicate"]
    # 3 identical files -> 2 are candidates, 1 preserved
    assert len(dup) == 2
    names = {i.path.name for i in dup}
    assert "keep.pdf" not in names


def test_trash_old(downloads: Path):
    items = build_clean_plan(downloads, old_days=180, trash_old=True)
    assert {i.path.name for i in items} == {"ancient.png"}


def test_trash_by_select_category(downloads: Path):
    items = build_clean_plan(downloads, old_days=180, select=lambda r: r.category == "문서")
    assert {i.path.name for i in items} == {"keep.pdf", "dup1.txt", "dup2.txt", "dup3.txt"}


def test_dry_run_trashes_nothing(downloads: Path, tmp_path: Path, fake_trash):
    res = run_clean(downloads, tmp_path / "ws", dry_run=True, trash_duplicates=True, trash_old=True)
    assert res.trashed_count == 0
    assert fake_trash == []  # nothing trashed in dry-run
    assert res.candidate_count > 0 and res.plan_token


def test_apply_blocked_with_wrong_token(downloads: Path, tmp_path: Path, fake_trash):
    with pytest.raises(ConfirmationError):
        run_clean(downloads, tmp_path / "ws", dry_run=False, trash_old=True, confirm_code="bad")
    assert fake_trash == []


def test_apply_sends_to_trash_with_token(downloads: Path, tmp_path: Path, fake_trash):
    preview = run_clean(downloads, tmp_path / "ws", dry_run=True, trash_old=True)
    res = run_clean(downloads, tmp_path / "ws", dry_run=False, trash_old=True,
                    confirm_code=preview.plan_token)
    assert res.trashed_count == 1
    assert any("ancient.png" in p for p in fake_trash)
    assert res.history_file and res.history_file.exists()


def test_protect_blocks_selecting_whole_duplicate_group(downloads: Path):
    # selecting ALL three identical dup files with protection on must raise
    dup_names = {"dup1.txt", "dup2.txt", "dup3.txt"}
    with pytest.raises(ValueError):
        build_clean_plan(
            downloads, old_days=180,
            select=lambda r: r.path.name in dup_names,
            protect_duplicate_groups=True,
        )


def test_protect_allows_partial_duplicate_selection(downloads: Path):
    # selecting only some copies (leaving >=1) is allowed
    items = build_clean_plan(
        downloads, old_days=180,
        select=lambda r: r.path.name in {"dup1.txt", "dup2.txt"},
        protect_duplicate_groups=True,
    )
    assert {i.path.name for i in items} == {"dup1.txt", "dup2.txt"}


def test_trash_empty_dirs_cascades_and_keeps_nonempty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    (d / "sub" / "nested").mkdir(parents=True)   # both empty -> should be removed
    (d / "hasfile").mkdir()
    (d / "hasfile" / "f.txt").write_text("y")     # non-empty -> kept
    (d / "keep.txt").write_text("x")

    trashed: list[str] = []
    fake = types.ModuleType("send2trash")
    fake.send2trash = lambda p: (trashed.append(str(p)), Path(p).rmdir())  # emulate real removal
    monkeypatch.setitem(sys.modules, "send2trash", fake)

    removed = trash_empty_dirs(d, target_root=tmp_path / "out")
    assert set(removed) == {str(d / "sub" / "nested"), str(d / "sub")}
    assert (d / "hasfile").exists()   # has a file -> kept
    assert (d / "keep.txt").exists()  # top-level file untouched


def test_execute_refuses_outside_scan_root(downloads: Path, tmp_path: Path, fake_trash):
    from download_organizer.models import CleanPlanItem

    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    items = [CleanPlanItem(path=outside, reason="selected", size=1)]
    outcome = execute_clean(items, tmp_path / "hist", confirm=True, scan_root=downloads)
    assert len(outcome.failures) == 1
    assert fake_trash == []  # never trashed (outside scan root)
