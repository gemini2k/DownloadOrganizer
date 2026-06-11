from __future__ import annotations

from pathlib import Path

import pytest

from download_organizer import safety
from download_organizer.organizer import build_move_plan, execute_plan, preview_undo, undo_move


@pytest.fixture
def applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"a")
    (d / "b.txt").write_bytes(b"b")
    plan = build_move_plan(d, tmp_path / "out", old_days=180)["plan"]
    outcome = execute_plan(plan, tmp_path / "hist", confirm=True, scan_root=d)
    return d, outcome.history_file


def test_preview_undo_does_not_move(applied):
    d, history = applied
    before = {p.name for p in (d.parent / "out").rglob("*") if p.is_file()}
    prev = preview_undo(history)
    assert len(prev.restorable) == 2
    assert prev.skipped == []
    # nothing moved by previewing
    after = {p.name for p in (d.parent / "out").rglob("*") if p.is_file()}
    assert before == after
    assert not (d / "a.pdf").exists()  # still organized, not restored


def test_preview_undo_flags_occupied_original(applied):
    d, history = applied
    (d / "a.pdf").write_text("blocker")  # original location now occupied
    prev = preview_undo(history)
    assert len(prev.restorable) == 1
    assert len(prev.skipped) == 1
    assert prev.skipped[0]["reason"] == "original location occupied"


def test_preview_matches_actual_undo(applied):
    d, history = applied
    (d / "a.pdf").write_text("blocker")
    prev = preview_undo(history)
    outcome = undo_move(history)
    assert outcome.restored == len(prev.restorable)
    assert len(outcome.skipped) == len(prev.skipped)
