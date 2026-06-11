# pyright: reportAny=false, reportUnusedCallResult=false
from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from .config import DEFAULT_OLD_DAYS, apply_user_config, default_download_path, default_workspace, write_default_config
from .logging_utils import setup_logger
from .models import MovePlanItem
from .organizer import preview_undo, undo_move
from .service import ConfirmationError, RunResult, run_clean, run_organizer


def _add_common_scan_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--scan-root", type=Path, default=default_download_path())
    p.add_argument("--output-root", type=Path, default=default_workspace())
    p.add_argument("--config", type=Path, default=None,
                   help="Path to a config.json overriding categories/old-days/blocked paths")
    p.add_argument("--old-days", type=int, default=None,
                   help=f"Old-file threshold in days (default: config or {DEFAULT_OLD_DAYS})")
    p.add_argument("--no-bookmarks", action="store_true", help="Skip browser bookmark analysis (privacy)")
    p.add_argument("--dup-mode", choices=["strict", "fast"], default="strict",
                   help="strict=full hash (exact), fast=first-1MB hash (faster, may over-report)")
    p.add_argument("--mask-bookmark-query", action="store_true",
                   help="Strip querystring/fragment from bookmark URLs in reports")
    p.add_argument("--exclude-domain", action="append", default=[], metavar="DOMAIN",
                   help="Exclude bookmarks whose domain contains this string (repeatable)")
    p.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True,
                   help="Scan subfolders (default: on). Use --no-recursive for top-level only.")
    p.add_argument("--exclude-dir", action="append", default=[], metavar="NAME",
                   help="Folder name to skip during recursive scan (repeatable)")
    p.add_argument("--date-grouping", choices=["none", "year", "month"], default="none",
                   help="Nest by modified date under each category (year=YYYY, month=YYYY-MM)")
    p.add_argument("--ext-grouping", action="store_true",
                   help="Nest by file extension under each category (e.g. 문서/pdf/)")
    p.add_argument("--include-category", action="append", default=[], metavar="CAT",
                   help="Only move these categories (repeatable). Default: all")
    p.add_argument("--exclude-category", action="append", default=[], metavar="CAT",
                   help="Skip these categories when moving (repeatable)")
    p.add_argument("--route-old", action="store_true",
                   help="Route old-file candidates to a _old_files review folder")
    p.add_argument("--route-duplicates", action="store_true",
                   help="Route duplicate candidates to a _duplicates review folder (no deletion)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe Download Organizer")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Dry-run: analyze, write reports, print plan token (no move)")
    _add_common_scan_args(analyze)

    apply = sub.add_parser("apply", help="Move files (requires --confirm-code from analyze)")
    _add_common_scan_args(apply)
    apply.add_argument("--confirm-code", required=True, metavar="TOKEN",
                       help="Plan token printed by `analyze` (binds apply to a reviewed plan)")

    # Backward-compatible alias. `run` (no --apply) == analyze. `run --apply` is rejected
    # and points users at the safer `apply` subcommand.
    run = sub.add_parser("run", help="[deprecated] alias for analyze")
    _add_common_scan_args(run)
    run.add_argument("--apply", action="store_true", help=argparse.SUPPRESS)
    run.add_argument("--confirm", action="store_true", help=argparse.SUPPRESS)

    # Recycle-Bin cleanup (recoverable). Dry-run unless --confirm-code is supplied.
    clean = sub.add_parser("clean", help="Send duplicates/old/selected files to the Recycle Bin (recoverable)")
    clean.add_argument("--scan-root", type=Path, default=default_download_path())
    clean.add_argument("--output-root", type=Path, default=default_workspace())
    clean.add_argument("--config", type=Path, default=None)
    clean.add_argument("--old-days", type=int, default=None)
    clean.add_argument("--dup-mode", choices=["strict", "fast"], default="strict")
    clean.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True)
    clean.add_argument("--exclude-dir", action="append", default=[], metavar="NAME")
    clean.add_argument("--trash-old", action="store_true", help="Trash old-file candidates")
    clean.add_argument("--trash-duplicates", action="store_true",
                       help="Trash duplicate copies (always keeps one per group)")
    clean.add_argument("--trash-category", action="append", default=[], metavar="CAT",
                       help="Trash files of this category (repeatable)")
    clean.add_argument("--confirm-code", default=None, metavar="TOKEN",
                       help="Clean token from the dry-run; omit to preview only")

    undo = sub.add_parser("undo", help="Undo a previous move history")
    undo.add_argument("--history-file", type=Path, required=True)
    undo.add_argument("--preview", action="store_true",
                      help="Show what would be restored/skipped without moving anything")

    init_cfg = sub.add_parser("init-config", help="Write an editable default config.json")
    init_cfg.add_argument("--path", type=Path, default=Path("download_organizer.config.json"))

    return parser


def _result_payload(r: RunResult, *, dry_run: bool) -> dict[str, object]:
    return {
        "status": "success",
        "dry_run": dry_run,
        "plan_token": r.plan_token,
        "dup_mode": r.dup_mode,
        "records": r.records_count,
        "planned_moves": r.move_count,
        "selected_moves": r.selected_count,
        "duplicate_groups": r.duplicate_group_count,
        "old_files": r.old_file_count,
        "bookmarks": r.bookmark_count,
        "moved": r.moved_count,
        "failures": r.failure_count,
        "history_file": str(r.history_file) if r.history_file else None,
        "download_reports": {k: str(v) for k, v in r.download_reports.items()},
        "bookmark_reports": {k: str(v) for k, v in r.bookmark_reports.items()},
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    logger = setup_logger((default_workspace() / "logs" / "download_organizer.log"))

    if args.command == "init-config":
        write_default_config(args.path)
        print({"status": "success", "config_written": str(args.path)})
        return 0

    if args.command == "undo":
        if args.preview:
            preview = preview_undo(args.history_file)
            print({"preview": True, "restorable": len(preview.restorable),
                   "skipped": len(preview.skipped),
                   "skipped_reasons": [s["reason"] for s in preview.skipped]})
            return 0
        outcome = undo_move(args.history_file)
        print({"restored": outcome.restored, "skipped": len(outcome.skipped),
               "history_file": str(args.history_file)})
        return 0

    if args.command == "clean":
        app_cfg = apply_user_config(args.config) if args.config is not None else None
        old_days = args.old_days if args.old_days is not None else (app_cfg.old_days if app_cfg else DEFAULT_OLD_DAYS)
        cats = set(args.trash_category)
        clean_select = (lambda r: r.category in cats) if cats else None
        dry_run = args.confirm_code is None
        try:
            res = run_clean(
                scan_root=args.scan_root, output_root=args.output_root,
                dry_run=dry_run, old_days=old_days, dup_mode=args.dup_mode,
                recursive=args.recursive, exclude_dirs=args.exclude_dir,
                trash_old=args.trash_old, trash_duplicates=args.trash_duplicates,
                select=clean_select, confirm_code=args.confirm_code,
            )
        except ConfirmationError as exc:
            print({"status": "blocked", "error": str(exc)})
            return 2
        except Exception as exc:  # noqa: BLE001
            logger.exception("clean failed")
            print({"status": "fail", "error": str(exc)})
            return 1
        payload = {
            "status": "success", "dry_run": dry_run, "clean_token": res.plan_token,
            "candidates": res.candidate_count, "by_reason": res.by_reason,
            "trashed": res.trashed_count, "failures": res.failure_count,
            "history_file": str(res.history_file) if res.history_file else None,
        }
        if dry_run and res.candidate_count:
            payload["hint"] = f"To trash (Recycle Bin): download-organizer clean ... --confirm-code {res.plan_token}"
        print(payload)
        return 0

    if args.command == "run" and args.apply:
        parser.error("`run --apply` is removed. Use `analyze` then `apply --confirm-code <token>`.")

    # Apply user config (categories / blocked paths / old-days), then resolve old_days.
    app_config = None
    if args.config is not None:
        try:
            app_config = apply_user_config(args.config)
        except Exception as exc:  # noqa: BLE001
            print({"status": "fail", "error": f"config load failed: {exc}"})
            return 1
    old_days = args.old_days if args.old_days is not None else (app_config.old_days if app_config else DEFAULT_OLD_DAYS)

    dry_run = args.command != "apply"
    confirm_code = getattr(args, "confirm_code", None)

    include = set(args.include_category)
    exclude = set(args.exclude_category)
    select: Callable[[MovePlanItem], bool] | None = None
    if include or exclude:
        def _select(item: MovePlanItem) -> bool:
            if include and item.category not in include:
                return False
            return item.category not in exclude
        select = _select

    try:
        result = run_organizer(
            scan_root=args.scan_root,
            output_root=args.output_root,
            dry_run=dry_run,
            confirm_move=not dry_run,
            old_days=old_days,
            include_bookmarks=not args.no_bookmarks,
            dup_mode=args.dup_mode,
            mask_query=args.mask_bookmark_query,
            exclude_domains=args.exclude_domain,
            recursive=args.recursive,
            exclude_dirs=args.exclude_dir,
            date_grouping=args.date_grouping,
            ext_grouping=args.ext_grouping,
            route_old=args.route_old,
            route_duplicates=args.route_duplicates,
            select=select,
            confirm_code=confirm_code,
        )
    except ConfirmationError as exc:
        print({"status": "blocked", "error": str(exc)})
        return 2
    except Exception as exc:  # noqa: BLE001
        logger.exception("run failed")
        print({"status": "fail", "error": str(exc)})
        return 1

    payload = _result_payload(result, dry_run=dry_run)
    if dry_run:
        payload["hint"] = f"To move files: download-organizer apply --confirm-code {result.plan_token}"
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
