from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_OLD_DAYS = 180

# 분류명은 그대로 정리 폴더명으로 쓰입니다(한글). config.json으로 변경 가능.
OTHERS_CATEGORY = "기타"

FILE_CATEGORIES: dict[str, set[str]] = {
    "문서": {".pdf", ".doc", ".docx", ".hwp", ".hwpx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv"},
    "이미지": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"},
    "동영상": {".mp4", ".mkv", ".avi", ".mov", ".wmv"},
    "오디오": {".mp3", ".wav", ".flac", ".m4a"},
    "압축파일": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "실행파일": {".exe", ".msi", ".bat", ".cmd", ".ps1"},
    "코드": {".py", ".js", ".ts", ".java", ".cpp", ".c", ".cs", ".go", ".rs", ".ipynb"},
}


# Keyword-based bookmark categories (matched against domain + title + url).
# Order matters: the first matching category wins.
BOOKMARK_CATEGORIES: dict[str, list[str]] = {
    "AI": ["openai", "claude", "anthropic", "gemini", "huggingface", "perplexity", "ollama"],
    "Development": ["github", "gitlab", "stackoverflow", "npm", "pypi", "docker", "nodejs", "visualstudio", "localhost"],
    "Public": ["go.kr", "data.go.kr", "g2b.go.kr", "law.go.kr", "juso.go.kr"],
    "News": ["news", "newspaper", "bbc", "cnn"],
    "Shopping": ["coupang", "gmarket", "11st", "amazon", "aliexpress"],
    "Education": ["coursera", "edx", "inflearn", "class", "lecture"],
    "Finance": ["bank", "finance", "stock", "securities"],
    "Reference": ["wikipedia", "docs", "documentation"],
}


# Snapshots of the built-in defaults so a loaded config can be reverted (reset_user_config).
_DEFAULT_FILE_CATEGORIES = {k: set(v) for k, v in FILE_CATEGORIES.items()}
_DEFAULT_BOOKMARK_CATEGORIES = {k: list(v) for k, v in BOOKMARK_CATEGORIES.items()}


def categorize_bookmark(domain: str, name: str, url: str) -> str:
    haystack = f"{domain} {name} {url}".lower()
    for category, keywords in BOOKMARK_CATEGORIES.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return "Etc"


def default_download_path() -> Path:
    return Path.home() / "Downloads"


def default_workspace() -> Path:
    return Path.cwd() / "workspace"


# User-supplied extra paths to block. Config can only ADD to the built-in blocklist,
# never remove from it, so a config file can never weaken the safety guarantees.
EXTRA_BLOCKED_ROOTS: list[Path] = []


def blocked_roots() -> list[Path]:
    roots = [
        Path("C:/Windows"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("C:/ProgramData"),
        Path.home() / "AppData",
        Path.home() / "Desktop",
        Path.home() / "Documents",
    ]
    return roots + list(EXTRA_BLOCKED_ROOTS)


@dataclass
class AppConfig:
    """Scalar settings resolved from a user config file (or defaults)."""

    old_days: int = DEFAULT_OLD_DAYS


def default_config_dict() -> dict[str, object]:
    """A starting config users can edit. Mirrors the built-in defaults."""
    return {
        "old_days": DEFAULT_OLD_DAYS,
        "file_categories": {cat: sorted(exts) for cat, exts in FILE_CATEGORIES.items()},
        "bookmark_categories": {cat: list(words) for cat, words in BOOKMARK_CATEGORIES.items()},
        "extra_blocked_roots": [],
    }


def write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(default_config_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def apply_user_config(path: Path) -> AppConfig:
    """Load a JSON config and apply overrides to module state. Returns scalar settings.

    Override rules:
    - ``file_categories`` / ``bookmark_categories``: if present, replace that section.
    - ``extra_blocked_roots``: ADDED to the built-in blocklist (never removes built-ins).
    - ``old_days``: scalar override.
    Missing keys keep the built-in defaults.
    """
    data = json.loads(path.read_text(encoding="utf-8"))

    file_cats = data.get("file_categories")
    if isinstance(file_cats, dict):
        FILE_CATEGORIES.clear()
        for category, exts in file_cats.items():
            FILE_CATEGORIES[str(category)] = {str(e).lower() for e in exts}

    bm_cats = data.get("bookmark_categories")
    if isinstance(bm_cats, dict):
        BOOKMARK_CATEGORIES.clear()
        for category, words in bm_cats.items():
            BOOKMARK_CATEGORIES[str(category)] = [str(w) for w in words]

    extra = data.get("extra_blocked_roots")
    if isinstance(extra, list):
        EXTRA_BLOCKED_ROOTS.clear()
        EXTRA_BLOCKED_ROOTS.extend(Path(str(p)) for p in extra)

    old_days = data.get("old_days")
    return AppConfig(old_days=int(old_days) if isinstance(old_days, (int, float)) else DEFAULT_OLD_DAYS)


def reset_user_config() -> None:
    """Restore the built-in defaults (undo any apply_user_config overrides)."""
    FILE_CATEGORIES.clear()
    FILE_CATEGORIES.update({k: set(v) for k, v in _DEFAULT_FILE_CATEGORIES.items()})
    BOOKMARK_CATEGORIES.clear()
    BOOKMARK_CATEGORIES.update({k: list(v) for k, v in _DEFAULT_BOOKMARK_CATEGORIES.items()})
    EXTRA_BLOCKED_ROOTS.clear()
