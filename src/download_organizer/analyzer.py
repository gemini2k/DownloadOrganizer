from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .models import FileRecord


def categorize_extension(ext: str) -> str:
    low = ext.lower()
    for category, exts in config.FILE_CATEGORIES.items():
        if low in exts:
            return category
    return config.OTHERS_CATEGORY


DupMode = str  # "fast" | "strict"


def _sha256_head(path: Path, max_bytes: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        hasher.update(f.read(max_bytes))
    return hasher.hexdigest()


def _sha256_full(path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _iter_files(
    scan_root: Path,
    recursive: bool,
    exclude_names: set[str],
    exclude_resolved: set[Path],
):
    """Yield files to analyze.

    Non-recursive (default): only files directly under scan_root; subfolders are
    never entered. Recursive: descend into subfolders, but prune any directory whose
    name is in `exclude_names`, whose resolved path is in `exclude_resolved`, or that
    is hidden (name starts with '.').
    """
    stack = [scan_root]
    while stack:
        folder = stack.pop()
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for item in entries:
            if item.is_dir():
                if not recursive:
                    continue
                if item.name.lower() in exclude_names or item.name.startswith("."):
                    continue
                try:
                    if item.resolve() in exclude_resolved:
                        continue
                except OSError:
                    continue
                stack.append(item)
            elif item.is_file():
                yield item


def analyze_files(
    scan_root: Path,
    old_days: int = 90,
    *,
    recursive: bool = False,
    exclude_dirs: list[str] | None = None,
    exclude_paths: list[Path] | None = None,
) -> list[FileRecord]:
    threshold = datetime.now() - timedelta(days=old_days)
    exclude_names = {d.lower() for d in (exclude_dirs or []) if d.strip()}
    exclude_resolved: set[Path] = set()
    for p in exclude_paths or []:
        try:
            exclude_resolved.add(p.resolve())
        except OSError:
            continue

    records: list[FileRecord] = []
    for item in _iter_files(scan_root, recursive, exclude_names, exclude_resolved):
        stat = item.stat()
        ext = item.suffix.lower()
        category = categorize_extension(ext)
        is_old = datetime.fromtimestamp(stat.st_mtime) < threshold
        records.append(
            FileRecord(
                path=item,
                size=stat.st_size,
                modified_ts=stat.st_mtime,
                extension=ext,
                category=category,
                # Cheap pre-group key; a full content hash is computed lazily only when
                # two files share a size (see duplicate_groups).
                duplicate_key=str(stat.st_size),
                is_old=is_old,
            )
        )
    return records


def summarize(records: list[FileRecord]) -> dict[str, int]:
    return dict(Counter(r.category for r in records))


def duplicate_groups(records: list[FileRecord], mode: DupMode = "strict") -> list[list[FileRecord]]:
    """Detect duplicate file groups.

    Two-pass for both speed and accuracy: first group by file size (cheap), then
    hash each multi-file size group. Unique-size files are never hashed.

    - ``strict`` (default): full SHA-256 content hash. Exact, no false positives.
    - ``fast``: hash only the first 1 MB. Faster on many large same-size files, but
      may over-report (files identical in their first 1 MB look the same). Duplicates
      are only *candidates* and are never auto-deleted, so over-reporting is low-risk.
    """
    hash_fn = _sha256_full if mode == "strict" else _sha256_head

    by_size: dict[int, list[FileRecord]] = {}
    for rec in records:
        by_size.setdefault(rec.size, []).append(rec)

    groups: list[list[FileRecord]] = []
    for size_group in by_size.values():
        if len(size_group) < 2:
            continue
        by_hash: dict[str, list[FileRecord]] = {}
        for rec in size_group:
            try:
                digest = hash_fn(rec.path)
            except OSError:
                continue
            by_hash.setdefault(digest, []).append(rec)
        groups.extend(group for group in by_hash.values() if len(group) > 1)
    return groups
