from __future__ import annotations

from pathlib import Path

import pytest

from download_organizer import safety
from download_organizer.config import blocked_roots


def test_blocked_roots_include_system_and_personal_folders():
    roots = {str(p) for p in blocked_roots()}
    assert any("Windows" in r for r in roots)
    assert any("Program Files" in r for r in roots)
    assert any("AppData" in r for r in roots)
    assert any("Desktop" in r for r in roots)
    assert any("Documents" in r for r in roots)


def test_ensure_safe_scan_root_rejects_system_path():
    with pytest.raises(ValueError):
        safety.ensure_safe_scan_root(Path("C:/Windows"))


def test_is_within():
    parent = Path.cwd()
    assert safety.is_within(parent / "a" / "b.txt", parent)
    assert safety.is_within(parent, parent)
    assert not safety.is_within(parent.parent, parent)


def test_ensure_source_within_scan_root(tmp_path: Path):
    scan = tmp_path / "Downloads"
    scan.mkdir()
    inside = scan / "file.txt"
    inside.write_text("x")
    safety.ensure_source_within_scan_root(inside, scan)  # no raise

    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x")
    with pytest.raises(ValueError):
        safety.ensure_source_within_scan_root(outside, scan)
