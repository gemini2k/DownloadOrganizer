"""Recycle-Bin cleanup. Files are sent to the OS trash (recoverable), never
permanently deleted. Mirrors the organize flow's safety model: dry-run by default,
plan-token confirmation, scan-root containment, logging, and a history record.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .analyzer import analyze_files, duplicate_groups
from .config import FILE_CATEGORIES  # noqa: F401  (kept for parity / future use)
from .models import CleanPlanItem, FileRecord, TrashOutcome
from .organizer import organized_dir_names
from .safety import ensure_safe_scan_root, ensure_source_within_scan_root

logger = logging.getLogger("download_organizer")


def compute_clean_token(items: list[CleanPlanItem]) -> str:
    payload = "\n".join(sorted(f"{i.reason}:{i.path}" for i in items))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _duplicate_extras(records: list[FileRecord], dup_mode: str) -> list[FileRecord]:
    """For each duplicate group, keep one copy and return the rest.

    The preserved copy is the one whose path sorts first (deterministic, typically the
    original/shortest location); every other copy in the group becomes a clean candidate.
    """
    extras: list[FileRecord] = []
    for group in duplicate_groups(records, mode=dup_mode):
        ordered = sorted(group, key=lambda r: str(r.path))
        extras.extend(ordered[1:])  # keep ordered[0]
    return extras


def build_clean_plan(
    scan_root: Path,
    *,
    old_days: int = 180,
    dup_mode: str = "strict",
    recursive: bool = False,
    exclude_dirs: list[str] | None = None,
    trash_old: bool = False,
    trash_duplicates: bool = False,
    select: Callable[[FileRecord], bool] | None = None,
    protect_duplicate_groups: bool = False,
) -> list[CleanPlanItem]:
    ensure_safe_scan_root(scan_root)
    skip_names = list(organized_dir_names()) + list(exclude_dirs or [])
    records = analyze_files(scan_root, old_days=old_days, recursive=recursive, exclude_dirs=skip_names)

    # Reason precedence so each path appears once: duplicate > old > selected.
    chosen: dict[Path, str] = {}
    if trash_duplicates:
        for rec in _duplicate_extras(records, dup_mode):
            chosen.setdefault(rec.path, "duplicate")
    if trash_old:
        for rec in records:
            if rec.is_old:
                chosen.setdefault(rec.path, "old")
    if select is not None:
        for rec in records:
            if select(rec):
                chosen.setdefault(rec.path, "selected")

    # Safety net: never let a clean remove EVERY copy of a duplicate group.
    if protect_duplicate_groups:
        for idx, group in enumerate(duplicate_groups(records, mode=dup_mode), start=1):
            members = {r.path for r in group}
            if members and members <= set(chosen):
                raise ValueError(
                    f"중복 그룹 {idx}의 모든 사본을 삭제할 수 없습니다. 최소 1개는 남겨주세요."
                )

    by_path = {r.path: r for r in records}
    return [
        CleanPlanItem(path=p, reason=reason, size=by_path[p].size)
        for p, reason in chosen.items()
    ]


def _send_to_trash(path: Path) -> None:
    """Send a single file to the OS Recycle Bin. Never falls back to permanent delete."""
    try:
        from send2trash import send2trash
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("휴지통 이동에는 send2trash가 필요합니다: pip install send2trash") from exc
    send2trash(str(path))


def execute_clean(
    items: list[CleanPlanItem], history_dir: Path, confirm: bool, scan_root: Path,
    progress: Callable[[int, int, str], None] | None = None,
) -> TrashOutcome:
    if not confirm:
        raise ValueError("Clean execution requires explicit confirmation.")

    history_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_file = history_dir / f"trash_history_{ts}.json"
    outcome = TrashOutcome(history_file=history_file)

    def _persist() -> None:
        history_file.write_text(
            json.dumps(
                {"note": "files sent to Recycle Bin; restore from there",
                 "trashed": outcome.trashed, "failures": outcome.failures},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    total = len(items)
    for done, item in enumerate(items, start=1):
        try:
            # Hard guard: only ever touch files inside the selected scan folder.
            ensure_source_within_scan_root(item.path, scan_root)
            _send_to_trash(item.path)
            outcome.trashed.append({"path": str(item.path), "reason": item.reason})
            logger.info("trashed (recycle bin): %s [%s]", item.path, item.reason)
            _persist()
        except Exception as exc:  # noqa: BLE001 - record and continue
            outcome.failures.append({"path": str(item.path), "error": str(exc)})
            logger.error("trash failed: %s (%s)", item.path, exc)
            _persist()
        if progress is not None:
            progress(done, total, str(item.path))

    _persist()
    logger.info("clean complete: trashed=%d failed=%d history=%s",
                len(outcome.trashed), len(outcome.failures), history_file)
    return outcome
