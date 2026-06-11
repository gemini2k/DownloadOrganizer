from __future__ import annotations

import json
from pathlib import Path

import pytest

from download_organizer import config
from download_organizer.analyzer import categorize_extension


@pytest.fixture(autouse=True)
def restore_config():
    """Snapshot and restore mutable config globals around each test."""
    file_snap = {k: set(v) for k, v in config.FILE_CATEGORIES.items()}
    bm_snap = {k: list(v) for k, v in config.BOOKMARK_CATEGORIES.items()}
    extra_snap = list(config.EXTRA_BLOCKED_ROOTS)
    yield
    config.FILE_CATEGORIES.clear(); config.FILE_CATEGORIES.update(file_snap)
    config.BOOKMARK_CATEGORIES.clear(); config.BOOKMARK_CATEGORIES.update(bm_snap)
    config.EXTRA_BLOCKED_ROOTS.clear(); config.EXTRA_BLOCKED_ROOTS.extend(extra_snap)


def test_write_and_load_default_config(tmp_path: Path):
    p = tmp_path / "config.json"
    config.write_default_config(p)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "file_categories" in data and "old_days" in data


def test_apply_user_config_overrides_categories_and_old_days(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "old_days": 30,
        "file_categories": {"ebooks": [".epub", ".MOBI"]},
    }), encoding="utf-8")

    cfg = config.apply_user_config(p)
    assert cfg.old_days == 30
    assert config.FILE_CATEGORIES == {"ebooks": {".epub", ".mobi"}}  # replaced + lowercased
    assert categorize_extension(".epub") == "ebooks"
    assert categorize_extension(".pdf") == "기타"  # old category gone -> fallback


def test_reset_user_config_restores_defaults(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "file_categories": {"ebooks": [".epub"]},
        "extra_blocked_roots": ["D:/X"],
    }), encoding="utf-8")
    config.apply_user_config(p)
    assert config.FILE_CATEGORIES == {"ebooks": {".epub"}}
    assert config.EXTRA_BLOCKED_ROOTS

    config.reset_user_config()
    assert "문서" in config.FILE_CATEGORIES          # built-in categories back
    assert config.EXTRA_BLOCKED_ROOTS == []          # extra blocks cleared


def test_extra_blocked_roots_only_adds(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"extra_blocked_roots": ["D:/Secret"]}), encoding="utf-8")
    config.apply_user_config(p)
    roots = {str(r) for r in config.blocked_roots()}
    assert any("Secret" in r for r in roots)       # added
    assert any("Windows" in r for r in roots)      # built-ins still present (cannot be weakened)
