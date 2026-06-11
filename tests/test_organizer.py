from __future__ import annotations

from pathlib import Path

import pytest

from download_organizer import safety
from download_organizer.analyzer import categorize_extension, duplicate_groups, analyze_files
from download_organizer.organizer import build_move_plan, execute_plan, undo_move


@pytest.fixture
def downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # tmp_path lives under AppData (blocked); bypass the system-path check for tests only.
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"hello pdf")
    (d / "b.jpg").write_bytes(b"image-bytes")
    (d / "dup1.txt").write_bytes(b"same content")
    (d / "dup2.txt").write_bytes(b"same content")
    return d


def test_categorize_extension():
    assert categorize_extension(".pdf") == "문서"
    assert categorize_extension(".PNG") == "이미지"
    assert categorize_extension(".unknownext") == "기타"


def test_duplicate_detection(downloads: Path):
    records = analyze_files(downloads, old_days=180)
    groups = duplicate_groups(records)
    assert len(groups) == 1
    assert {r.path.name for r in groups[0]} == {"dup1.txt", "dup2.txt"}


def test_dry_run_does_not_move(downloads: Path, tmp_path: Path):
    target = tmp_path / "out" / "organized"
    context = build_move_plan(downloads, target, old_days=180)
    assert len(context["plan"]) == 4
    # nothing should have been created/moved by planning
    assert not target.exists()
    assert (downloads / "a.pdf").exists()


def test_execute_then_undo_roundtrip(downloads: Path, tmp_path: Path):
    target = tmp_path / "out" / "organized"
    history = tmp_path / "out" / "history"
    context = build_move_plan(downloads, target, old_days=180)

    outcome = execute_plan(context["plan"], history, confirm=True, scan_root=downloads)
    assert outcome.failures == []
    assert not (downloads / "a.pdf").exists()  # moved out

    restored = undo_move(outcome.history_file)
    assert restored.restored == 4
    assert (downloads / "a.pdf").exists()  # back in place


def test_execute_plan_reports_progress(downloads: Path, tmp_path: Path):
    context = build_move_plan(downloads, tmp_path / "out", old_days=180)
    total_files = len(context["plan"])
    calls: list[tuple[int, int]] = []
    execute_plan(context["plan"], tmp_path / "h", confirm=True, scan_root=downloads,
                 progress=lambda done, total, path: calls.append((done, total)))
    assert len(calls) == total_files          # one callback per file
    assert calls[-1] == (total_files, total_files)  # ends at 100%
    assert [c[0] for c in calls] == list(range(1, total_files + 1))  # monotonic


def test_execute_requires_confirm(downloads: Path, tmp_path: Path):
    context = build_move_plan(downloads, tmp_path / "o", old_days=180)
    with pytest.raises(ValueError):
        execute_plan(context["plan"], tmp_path / "h", confirm=False, scan_root=downloads)


def test_undo_skips_when_original_occupied(downloads: Path, tmp_path: Path):
    target = tmp_path / "out" / "organized"
    history = tmp_path / "out" / "history"
    context = build_move_plan(downloads, target, old_days=180)
    outcome = execute_plan(context["plan"], history, confirm=True, scan_root=downloads)

    # Re-create a file at one original location -> undo must NOT overwrite it.
    (downloads / "a.pdf").write_text("new content")
    result = undo_move(outcome.history_file)
    assert result.restored == 3
    assert len(result.skipped) == 1
    assert (downloads / "a.pdf").read_text() == "new content"


def test_execute_refuses_source_outside_scan_root(downloads: Path, tmp_path: Path):
    from download_organizer.models import MovePlanItem

    outside = tmp_path / "secret.txt"
    outside.write_text("do not touch")
    bad_plan = [MovePlanItem(src=outside, dst=tmp_path / "out" / "secret.txt", category="documents")]
    outcome = execute_plan(bad_plan, tmp_path / "h", confirm=True, scan_root=downloads)
    assert len(outcome.failures) == 1
    assert outside.exists()  # untouched
