from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from download_organizer import safety
from download_organizer.organizer import build_move_plan, compute_plan_token
from download_organizer.service import ConfirmationError, build_preview, run_organizer


@pytest.fixture
def downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"pdf")
    (d / "b.jpg").write_bytes(b"img")
    (d / "c.txt").write_bytes(b"txt")
    return d


# --- E: date grouping ------------------------------------------------------- #
def test_date_grouping_year(downloads: Path, tmp_path: Path):
    # pin a known mtime so the year subfolder is deterministic
    ts = time.mktime((2021, 6, 15, 12, 0, 0, 0, 0, -1))
    for f in downloads.iterdir():
        os.utime(f, (ts, ts))

    context = build_move_plan(downloads, tmp_path / "out", old_days=180, date_grouping="year")
    for item in context["plan"]:
        assert item.dst.parent.name == "2021"  # category/2021/<file>


def test_date_grouping_month(downloads: Path, tmp_path: Path):
    ts = time.mktime((2021, 6, 15, 12, 0, 0, 0, 0, -1))
    for f in downloads.iterdir():
        os.utime(f, (ts, ts))
    context = build_move_plan(downloads, tmp_path / "out", old_days=180, date_grouping="month")
    assert all(item.dst.parent.name == "2021-06" for item in context["plan"])


def test_date_grouping_none_default(downloads: Path, tmp_path: Path):
    context = build_move_plan(downloads, tmp_path / "out", old_days=180)
    # no date subfolder -> parent is the category folder itself
    assert all(item.dst.parent.name == item.category for item in context["plan"])


# --- ext grouping ----------------------------------------------------------- #
def test_ext_grouping(downloads: Path, tmp_path: Path):
    plan = build_move_plan(downloads, tmp_path / "out", old_days=180, ext_grouping=True)["plan"]
    by_name = {Path(p.src).name: Path(p.dst) for p in plan}
    # 분류/확장자/파일  -> 문서/pdf/a.pdf, 이미지/jpg/b.jpg
    assert by_name["a.pdf"].parent.name == "pdf"
    assert by_name["a.pdf"].parent.parent.name == "문서"
    assert by_name["b.jpg"].parent.name == "jpg"


def test_ext_grouping_no_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    d.mkdir()
    (d / "README").write_bytes(b"x")
    plan = build_move_plan(d, tmp_path / "out", old_days=180, ext_grouping=True)["plan"]
    assert Path(plan[0].dst).parent.name == "확장자없음"


def test_ext_and_date_grouping_order(downloads: Path, tmp_path: Path):
    ts = time.mktime((2021, 6, 15, 12, 0, 0, 0, 0, -1))
    for f in downloads.iterdir():
        os.utime(f, (ts, ts))
    plan = build_move_plan(downloads, tmp_path / "out", old_days=180,
                           ext_grouping=True, date_grouping="year")["plan"]
    dst = next(Path(p.dst) for p in plan if Path(p.src).name == "a.pdf")
    # 분류/확장자/날짜/파일 -> 문서/pdf/2021/a.pdf
    assert dst.parent.name == "2021"
    assert dst.parent.parent.name == "pdf"
    assert dst.parent.parent.parent.name == "문서"


# --- A: selective apply ----------------------------------------------------- #
def test_selective_apply_moves_only_selected(downloads: Path, tmp_path: Path):
    ws = tmp_path / "ws"
    preview = build_preview(downloads, ws, old_days=180, include_bookmarks=False)

    # select everything except the .jpg
    select = lambda i: i.src.suffix != ".jpg"
    subset = [i for i in preview.plan if select(i)]
    token = compute_plan_token(subset)

    result = run_organizer(
        scan_root=downloads, output_root=ws,
        dry_run=False, confirm_move=True, old_days=180, include_bookmarks=False,
        select=select, confirm_code=token,
    )
    assert result.selected_count == 2
    assert result.moved_count == 2
    assert (downloads / "b.jpg").exists()          # excluded -> stays
    assert not (downloads / "a.pdf").exists()       # selected -> moved


def test_selective_apply_token_is_subset_bound(downloads: Path, tmp_path: Path):
    ws = tmp_path / "ws"
    preview = build_preview(downloads, ws, old_days=180, include_bookmarks=False)
    full_token = preview.plan_token
    select = lambda i: i.src.suffix != ".jpg"

    # using the FULL-plan token for a filtered apply must be rejected
    with pytest.raises(ConfirmationError):
        run_organizer(
            scan_root=downloads, output_root=ws,
            dry_run=False, confirm_move=True, old_days=180, include_bookmarks=False,
            select=select, confirm_code=full_token,
        )
    assert (downloads / "a.pdf").exists()  # nothing moved
