from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast

from .bookmarks import analyze_bookmarks, duplicate_urls
from .cleaner import build_clean_plan, compute_clean_token, execute_clean
from .models import CleanPlanItem, FileRecord, MovePlanItem
from .organizer import build_move_plan, compute_plan_token, execute_plan
from .reports import write_bookmark_reports, write_download_reports


@dataclass
class Preview:
    """Full dry-run analysis used by both the CLI and the web UI."""

    scan_root: Path
    records: list[FileRecord]
    plan: list[MovePlanItem]
    duplicates: list[list[FileRecord]]
    old_files: list[FileRecord]
    summary: dict[str, int]
    bookmarks: list[dict[str, str]]
    plan_token: str
    dup_mode: str
    masked: bool
    recursive: bool = False
    bookmark_duplicates: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RunResult:
    records_count: int
    move_count: int
    selected_count: int
    duplicate_group_count: int
    old_file_count: int
    bookmark_count: int
    plan_token: str
    dup_mode: str
    history_file: Path | None
    moved_count: int
    failure_count: int
    download_reports: dict[str, Path]
    bookmark_reports: dict[str, Path]


class ConfirmationError(Exception):
    """Raised when an apply is attempted without a matching plan token."""


@dataclass
class CleanResult:
    plan_token: str
    candidate_count: int
    by_reason: dict[str, int]
    items: list[CleanPlanItem]
    trashed_count: int
    failure_count: int
    history_file: Path | None


def run_clean(
    scan_root: Path,
    output_root: Path,
    *,
    dry_run: bool,
    old_days: int = 180,
    dup_mode: str = "strict",
    recursive: bool = False,
    exclude_dirs: list[str] | None = None,
    trash_old: bool = False,
    trash_duplicates: bool = False,
    select: Callable[[FileRecord], bool] | None = None,
    protect_duplicate_groups: bool = False,
    confirm_code: str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> CleanResult:
    """Send selected files to the Recycle Bin (recoverable). Dry-run unless a matching
    confirm_code (plan token) is supplied."""
    items = build_clean_plan(
        scan_root,
        old_days=old_days,
        dup_mode=dup_mode,
        recursive=recursive,
        exclude_dirs=exclude_dirs,
        trash_old=trash_old,
        trash_duplicates=trash_duplicates,
        select=select,
        protect_duplicate_groups=protect_duplicate_groups,
    )
    token = compute_clean_token(items)
    by_reason: dict[str, int] = {}
    for it in items:
        by_reason[it.reason] = by_reason.get(it.reason, 0) + 1

    history_file: Path | None = None
    trashed = 0
    failures = 0
    if not dry_run:
        if confirm_code != token:
            raise ConfirmationError(
                f"Confirmation token mismatch. Expected current clean token '{token}'."
            )
        outcome = execute_clean(items, output_root / "history", confirm=True, scan_root=scan_root,
                                progress=progress)
        history_file = outcome.history_file
        trashed = len(outcome.trashed)
        failures = len(outcome.failures)

    return CleanResult(
        plan_token=token,
        candidate_count=len(items),
        by_reason=by_reason,
        items=items,
        trashed_count=trashed,
        failure_count=failures,
        history_file=history_file,
    )


def build_preview(
    scan_root: Path,
    output_root: Path,
    *,
    old_days: int,
    include_bookmarks: bool = True,
    dup_mode: str = "strict",
    mask_query: bool = False,
    exclude_domains: list[str] | None = None,
    recursive: bool = False,
    exclude_dirs: list[str] | None = None,
    date_grouping: str = "none",
    ext_grouping: bool = False,
    route_old: bool = False,
    route_duplicates: bool = False,
) -> Preview:
    target_root = output_root / "organized_files"
    context = build_move_plan(
        scan_root=scan_root,
        target_root=target_root,
        old_days=old_days,
        dup_mode=dup_mode,
        recursive=recursive,
        exclude_dirs=exclude_dirs,
        date_grouping=date_grouping,
        ext_grouping=ext_grouping,
        route_old=route_old,
        route_duplicates=route_duplicates,
    )
    bookmarks = (
        analyze_bookmarks(mask_query=mask_query, exclude_domains=exclude_domains) if include_bookmarks else []
    )
    return Preview(
        scan_root=scan_root,
        records=cast(list[FileRecord], context["records"]),
        plan=cast(list[MovePlanItem], context["plan"]),
        duplicates=cast(list[list[FileRecord]], context["duplicates"]),
        old_files=cast(list[FileRecord], context["old_files"]),
        summary=cast("dict[str, int]", context["summary"]),
        bookmarks=bookmarks,
        plan_token=cast(str, context["plan_token"]),
        dup_mode=dup_mode,
        masked=mask_query,
        recursive=recursive,
        bookmark_duplicates=duplicate_urls(bookmarks),
    )


def run_organizer(
    scan_root: Path,
    output_root: Path,
    *,
    dry_run: bool,
    confirm_move: bool,
    old_days: int,
    include_bookmarks: bool = True,
    dup_mode: str = "strict",
    mask_query: bool = False,
    exclude_domains: list[str] | None = None,
    recursive: bool = False,
    exclude_dirs: list[str] | None = None,
    date_grouping: str = "none",
    ext_grouping: bool = False,
    route_old: bool = False,
    route_duplicates: bool = False,
    select: Callable[[MovePlanItem], bool] | None = None,
    confirm_code: str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> RunResult:
    report_root = output_root / "reports"
    history_root = output_root / "history"

    preview = build_preview(
        scan_root=scan_root,
        output_root=output_root,
        old_days=old_days,
        include_bookmarks=include_bookmarks,
        dup_mode=dup_mode,
        mask_query=mask_query,
        exclude_domains=exclude_domains,
        recursive=recursive,
        exclude_dirs=exclude_dirs,
        date_grouping=date_grouping,
        ext_grouping=ext_grouping,
        route_old=route_old,
        route_duplicates=route_duplicates,
    )

    # Selective apply: only the chosen items are moved. The token is computed over the
    # exact subset being applied, so apply stays bound to precisely what was reviewed.
    plan_to_apply = preview.plan if select is None else [i for i in preview.plan if select(i)]
    apply_token = compute_plan_token(plan_to_apply)

    # Plan-binding confirmation: the token must match the (filtered) plan we just rebuilt.
    if not dry_run:
        if not confirm_move:
            raise ConfirmationError("Apply requires explicit confirmation.")
        if confirm_code != apply_token:
            raise ConfirmationError(
                f"Confirmation token mismatch. Expected current plan token '{apply_token}'. "
                "Run analyze again with the same selection and pass the printed token."
            )

    routed = [name for name, on in (("old->_old_files", route_old),
                                    ("duplicates->_duplicates", route_duplicates)) if on]
    routing = ", ".join(routed) if routed else "category only"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    download_reports = write_download_reports(
        report_root, timestamp, preview.records, preview.plan, preview.duplicates,
        dup_mode=dup_mode, recursive=recursive, date_grouping=date_grouping, routing=routing,
        ext_grouping=ext_grouping,
    )
    bookmark_reports: dict[str, Path] = {}
    if include_bookmarks:
        bookmark_reports = write_bookmark_reports(report_root, timestamp, preview.bookmarks, masked=mask_query)

    history_file: Path | None = None
    moved_count = 0
    failure_count = 0
    if not dry_run:
        outcome = execute_plan(plan_to_apply, history_root, confirm=confirm_move, scan_root=scan_root,
                               progress=progress)
        history_file = outcome.history_file
        moved_count = len(outcome.moved)
        failure_count = len(outcome.failures)

    return RunResult(
        records_count=len(preview.records),
        move_count=len(preview.plan),
        selected_count=len(plan_to_apply),
        duplicate_group_count=len(preview.duplicates),
        old_file_count=len(preview.old_files),
        bookmark_count=len(preview.bookmarks),
        plan_token=apply_token,
        dup_mode=dup_mode,
        history_file=history_file,
        moved_count=moved_count,
        failure_count=failure_count,
        download_reports=download_reports,
        bookmark_reports=bookmark_reports,
    )
