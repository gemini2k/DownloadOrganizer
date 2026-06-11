from __future__ import annotations

from pathlib import Path

import pytest

from download_organizer import safety
from download_organizer.analyzer import analyze_files, duplicate_groups
from download_organizer.bookmarks import _walk_nodes, mask_url_query
from download_organizer.reports import write_download_reports
from download_organizer.service import ConfirmationError, build_preview, run_organizer


@pytest.fixture
def downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(safety, "blocked_roots", lambda: [])
    d = tmp_path / "Downloads"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"pdf-bytes")
    (d / "b.jpg").write_bytes(b"another-image")
    return d


# --- P1: analyze never moves ------------------------------------------------ #
def test_analyze_moves_nothing(downloads: Path, tmp_path: Path):
    before = {p.name for p in downloads.iterdir()}
    result = run_organizer(
        scan_root=downloads, output_root=tmp_path / "ws",
        dry_run=True, confirm_move=False, old_days=180, include_bookmarks=False,
    )
    assert result.history_file is None
    assert result.moved_count == 0
    assert {p.name for p in downloads.iterdir()} == before  # untouched


# --- P1: apply blocked without / with wrong token --------------------------- #
def test_apply_blocked_without_token(downloads: Path, tmp_path: Path):
    with pytest.raises(ConfirmationError):
        run_organizer(
            scan_root=downloads, output_root=tmp_path / "ws",
            dry_run=False, confirm_move=True, old_days=180, include_bookmarks=False,
            confirm_code=None,
        )
    assert (downloads / "a.pdf").exists()  # still there


def test_apply_blocked_with_wrong_token(downloads: Path, tmp_path: Path):
    with pytest.raises(ConfirmationError):
        run_organizer(
            scan_root=downloads, output_root=tmp_path / "ws",
            dry_run=False, confirm_move=True, old_days=180, include_bookmarks=False,
            confirm_code="deadbeef0000",
        )
    assert (downloads / "a.pdf").exists()


def test_apply_succeeds_with_matching_token(downloads: Path, tmp_path: Path):
    ws = tmp_path / "ws"
    analyzed = build_preview(downloads, ws, old_days=180, include_bookmarks=False)
    result = run_organizer(
        scan_root=downloads, output_root=ws,
        dry_run=False, confirm_move=True, old_days=180, include_bookmarks=False,
        confirm_code=analyzed.plan_token,
    )
    assert result.moved_count == 2
    assert not (downloads / "a.pdf").exists()  # moved out


# --- P2: timestamped reports do not overwrite ------------------------------- #
def test_reports_do_not_overwrite(downloads: Path, tmp_path: Path):
    records = analyze_files(downloads, old_days=180)
    report_dir = tmp_path / "reports"
    r1 = write_download_reports(report_dir, "20260101_010101", records, [], [])
    r2 = write_download_reports(report_dir, "20260101_020202", records, [], [])
    assert r1["md"] != r2["md"]
    assert {p.name for p in report_dir.glob("*.md")} == {r1["md"].name, r2["md"].name}
    assert len(list(report_dir.glob("download_organizer_report_*"))) == 6  # 2 runs x 3 formats


# --- P2: bookmark masking on/off -------------------------------------------- #
def test_mask_url_query():
    url = "https://example.com/path?token=secret&id=42#frag"
    assert mask_url_query(url) == "https://example.com/path"
    assert mask_url_query("https://example.com/x") == "https://example.com/x"


def _fake_nodes():
    return [{"type": "url", "name": "n", "url": "https://example.com/p?token=secret"}]


def test_walk_nodes_masking_on_off():
    off = _walk_nodes(_fake_nodes(), ["root"], "chrome", mask_query=False, exclude_domains=[])
    on = _walk_nodes(_fake_nodes(), ["root"], "chrome", mask_query=True, exclude_domains=[])
    assert "token=secret" in off[0]["url"]
    assert "token" not in on[0]["url"]


def test_walk_nodes_exclude_domain():
    rows = _walk_nodes(_fake_nodes(), ["root"], "chrome", mask_query=False, exclude_domains=["example.com"])
    assert rows == []


# --- P3: fast vs strict duplicate detection --------------------------------- #
def test_fast_vs_strict_duplicate_modes(tmp_path: Path):
    d = tmp_path / "dl"
    d.mkdir()
    head = b"X" * (1024 * 1024)  # identical first 1 MB
    (d / "a.bin").write_bytes(head + b"AAA")  # same size, different tail
    (d / "b.bin").write_bytes(head + b"BBB")
    records = analyze_files(d, old_days=180)

    fast = duplicate_groups(records, mode="fast")     # only hashes first 1 MB -> looks identical
    strict = duplicate_groups(records, mode="strict")  # full hash -> different

    assert len(fast) == 1 and len(fast[0]) == 2  # fast over-reports
    assert strict == []                           # strict is exact
