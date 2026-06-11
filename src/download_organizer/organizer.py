# pyright: reportAny=false, reportUnusedCallResult=false
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import config
from .analyzer import analyze_files, duplicate_groups, summarize
from .models import FileRecord, MoveOutcome, MovePlanItem, UndoOutcome, UndoPreview
from .safety import ensure_safe_scan_root, ensure_source_within_scan_root

logger = logging.getLogger("download_organizer")

# Dedicated review buckets for routed files (never auto-deleted, just gathered).
OLD_FILES_DIR = "오래된파일"
DUPLICATES_DIR = "중복파일"


def organized_dir_names() -> set[str]:
    """Folder names our own organize step creates; auto-excluded from a recursive
    scan so we never re-scan (and re-shuffle) files we already organized.

    Computed dynamically so a user config that changes the categories is respected.
    """
    return set(config.FILE_CATEGORIES) | {config.OTHERS_CATEGORY, OLD_FILES_DIR, DUPLICATES_DIR}


def compute_plan_token(plan: list[MovePlanItem]) -> str:
    """Short, deterministic fingerprint of a move plan.

    `apply` requires the token that `analyze` printed. If the download folder
    changes between analyze and apply, the recomputed token no longer matches,
    so a stale or unreviewed plan cannot be applied by accident.
    """
    payload = "\n".join(sorted(f"{p.src}->{p.dst}" for p in plan))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _date_subdir(rec: FileRecord, date_grouping: str) -> str:
    """Optional date subfolder under the category, based on the file's modified date."""
    if date_grouping == "year":
        return datetime.fromtimestamp(rec.modified_ts).strftime("%Y")
    if date_grouping == "month":
        return datetime.fromtimestamp(rec.modified_ts).strftime("%Y-%m")
    return ""


def _ext_subdir(rec: FileRecord) -> str:
    """Extension subfolder name (dot stripped, lowercase). No extension -> 확장자없음."""
    return rec.extension.lstrip(".").lower() if rec.extension else "확장자없음"


def build_move_plan(
    scan_root: Path,
    target_root: Path,
    old_days: int = 90,
    dup_mode: str = "strict",
    *,
    recursive: bool = False,
    exclude_dirs: list[str] | None = None,
    date_grouping: str = "none",
    ext_grouping: bool = False,
    route_old: bool = False,
    route_duplicates: bool = False,
) -> dict[str, object]:
    ensure_safe_scan_root(scan_root)
    # In recursive mode, skip our own organized output folders and any user-listed dirs,
    # and never descend into the target_root itself (in case it lives under scan_root).
    skip_names = list(organized_dir_names()) + list(exclude_dirs or [])
    records = analyze_files(
        scan_root,
        old_days=old_days,
        recursive=recursive,
        exclude_dirs=skip_names,
        exclude_paths=[target_root],
    )
    duplicates = duplicate_groups(records, mode=dup_mode)
    dup_paths = {r.path for group in duplicates for r in group}

    plan: list[MovePlanItem] = []
    claimed: set[Path] = set()  # destinations reserved by earlier plan items this run

    for rec in records:
        # Routing precedence: duplicates -> old -> normal category. Routed files go to a
        # flat review bucket (no date subfolder) so each group/bucket stays together.
        if route_duplicates and rec.path in dup_paths:
            label, use_date = DUPLICATES_DIR, False
        elif route_old and rec.is_old:
            label, use_date = OLD_FILES_DIR, False
        else:
            label, use_date = rec.category, True

        # Layout: 분류 / [확장자] / [날짜] / 파일. Routed review buckets stay flat (use_date=False).
        category_dir = target_root / label
        if use_date and ext_grouping:
            category_dir = category_dir / _ext_subdir(rec)
        date_sub = _date_subdir(rec, date_grouping) if use_date else ""
        if date_sub:
            category_dir = category_dir / date_sub
        dst = category_dir / rec.path.name
        if dst.exists() or dst in claimed:
            stem = rec.path.stem
            suffix = rec.path.suffix
            idx = 1
            while True:
                alt = category_dir / f"{stem}_{idx}{suffix}"
                if not alt.exists() and alt not in claimed:
                    dst = alt
                    break
                idx += 1
        claimed.add(dst)
        plan.append(MovePlanItem(src=rec.path, dst=dst, category=label))

    logger.info(
        "scan: root=%s files=%d planned=%d duplicates=%d old=%d recursive=%s",
        scan_root, len(records), len(plan), len(duplicates), sum(r.is_old for r in records), recursive,
    )
    return {
        "records": records,
        "summary": summarize(records),
        "duplicates": duplicates,
        "old_files": [r for r in records if r.is_old],
        "plan": plan,
        "plan_token": compute_plan_token(plan),
    }


def execute_plan(
    plan: list[MovePlanItem], history_dir: Path, confirm: bool, scan_root: Path,
    progress: Callable[[int, int, str], None] | None = None,
) -> MoveOutcome:
    if not confirm:
        raise ValueError("Move execution requires explicit confirmation.")

    history_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_file = history_dir / f"move_history_{ts}.json"
    outcome = MoveOutcome(history_file=history_file)

    def _persist() -> None:
        history_file.write_text(
            json.dumps({"moved": outcome.moved, "failures": outcome.failures}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    total = len(plan)
    for done, item in enumerate(plan, start=1):
        try:
            # Hard guard: never touch a file outside the selected download folder.
            ensure_source_within_scan_root(item.src, scan_root)
            # Never overwrite an existing destination, even if it appeared after planning.
            if item.dst.exists():
                raise FileExistsError(f"Destination already exists: {item.dst}")
            item.dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item.src), str(item.dst))
            outcome.moved.append({"src": str(item.src), "dst": str(item.dst), "category": item.category})
            logger.info("moved: %s -> %s", item.src, item.dst)
            _persist()  # incremental write so an undo is always possible after a mid-run failure
        except Exception as exc:  # noqa: BLE001 - record and continue, do not abort the whole run
            outcome.failures.append({"src": str(item.src), "dst": str(item.dst), "error": str(exc)})
            logger.error("move failed: %s -> %s (%s)", item.src, item.dst, exc)
            _persist()
        if progress is not None:
            progress(done, total, str(item.src))

    _persist()
    logger.info("apply complete: moved=%d failed=%d history=%s",
                len(outcome.moved), len(outcome.failures), history_file)
    return outcome


def _undo_skip_reason(src: Path, dst: Path) -> str | None:
    """Why this row can't be restored, or None if it's restorable."""
    if not dst.exists():
        return "moved file no longer exists"
    if src.exists():
        # Safety: never overwrite a file that re-appeared at the original location.
        return "original location occupied"
    return None


def preview_undo(history_file: Path) -> UndoPreview:
    """Report what an undo WOULD restore/skip, without moving anything."""
    data = json.loads(history_file.read_text(encoding="utf-8"))
    moved = data.get("moved", [])
    preview = UndoPreview()
    for row in reversed(moved):
        src, dst = Path(row["src"]), Path(row["dst"])
        reason = _undo_skip_reason(src, dst)
        entry = {"src": str(src), "dst": str(dst)}
        if reason:
            preview.skipped.append({**entry, "reason": reason})
        else:
            preview.restorable.append(entry)
    return preview


def undo_move(history_file: Path) -> UndoOutcome:
    data = json.loads(history_file.read_text(encoding="utf-8"))
    moved = data.get("moved", [])
    outcome = UndoOutcome()
    for row in reversed(moved):
        src = Path(row["src"])
        dst = Path(row["dst"])
        reason = _undo_skip_reason(src, dst)
        if reason:
            outcome.skipped.append({"src": str(src), "dst": str(dst), "reason": reason})
            if reason == "original location occupied":
                logger.warning("undo skipped (original occupied): %s", src)
            continue
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))
        outcome.restored += 1
        logger.info("restored: %s -> %s", dst, src)
    logger.info("undo complete: restored=%d skipped=%d from %s",
                outcome.restored, len(outcome.skipped), history_file)
    return outcome


def plan_to_dict_rows(plan: list[MovePlanItem]) -> list[dict[str, str]]:
    return [{"src": str(p.src), "dst": str(p.dst), "category": p.category} for p in plan]
