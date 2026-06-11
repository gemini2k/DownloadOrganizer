# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnusedCallResult=false
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from .models import FileRecord, MovePlanItem


# --------------------------------------------------------------------------- #
# DataFrame builders
# --------------------------------------------------------------------------- #
def _records_df(records: list[FileRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "path": str(r.path),
                "size": r.size,
                "extension": r.extension,
                "category": r.category,
                "modified": pd.to_datetime(r.modified_ts, unit="s"),
                "is_old": r.is_old,
            }
            for r in records
        ]
    )


def _plan_df(plan: list[MovePlanItem]) -> pd.DataFrame:
    return pd.DataFrame([{"src": str(p.src), "dst": str(p.dst), "category": p.category} for p in plan])


def _duplicates_df(duplicates: list[list[FileRecord]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for idx, group in enumerate(duplicates, start=1):
        for rec in group:
            rows.append({"group": idx, "path": str(rec.path), "size": rec.size, "category": rec.category})
    return pd.DataFrame(rows)


def _bookmarks_df(bookmarks: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(bookmarks)


# --------------------------------------------------------------------------- #
# Download folder report (files / plan / duplicates / old files)
# --------------------------------------------------------------------------- #
def _download_markdown(
    records: list[FileRecord], plan: list[MovePlanItem], duplicates: list[list[FileRecord]],
    dup_mode: str, recursive: bool, date_grouping: str, routing: str, ext_grouping: bool
) -> str:
    category_counts = Counter(r.category for r in records)
    category_size: Counter[str] = Counter()
    for r in records:
        category_size[r.category] += r.size
    old_files = [r for r in records if r.is_old]
    total_size = sum(r.size for r in records)

    lines = [
        "# Download Organizer Report",
        "",
        "## Overview",
        f"- scan scope: {'recursive (subfolders included)' if recursive else 'top-level only'}",
        f"- extension grouping: {'on' if ext_grouping else 'off'}",
        f"- date grouping: {date_grouping}",
        f"- routing: {routing}",
        f"- total files: {len(records)}",
        f"- total size: {total_size / (1024 * 1024):.2f} MB",
        f"- planned moves: {len(plan)}",
        f"- duplicate groups: {len(duplicates)} (mode: {dup_mode})",
        f"- old files: {len(old_files)}",
        "",
        "## File Category Summary",
    ]
    for category, count in sorted(category_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {category}: {count} files, {category_size[category] / (1024 * 1024):.2f} MB")

    lines.extend(["", "## Old File Candidates", f"- total: {len(old_files)}"])
    for rec in old_files[:50]:
        lines.append(f"- {rec.path.name} ({rec.size / 1024:.1f} KB)")

    lines.extend(["", "## Duplicate Groups", f"- groups: {len(duplicates)}"])
    for idx, group in enumerate(duplicates, start=1):
        lines.append(f"- group {idx}: " + ", ".join(g.path.name for g in group))

    return "\n".join(lines)


def write_download_reports(
    report_dir: Path,
    timestamp: str,
    records: list[FileRecord],
    plan: list[MovePlanItem],
    duplicates: list[list[FileRecord]],
    dup_mode: str = "strict",
    recursive: bool = False,
    date_grouping: str = "none",
    routing: str = "category only",
    ext_grouping: bool = False,
) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    base = f"download_organizer_report_{timestamp}"
    md_path = report_dir / f"{base}.md"
    html_path = report_dir / f"{base}.html"
    xlsx_path = report_dir / f"{base}.xlsx"

    md_path.write_text(
        _download_markdown(records, plan, duplicates, dup_mode, recursive, date_grouping, routing, ext_grouping),
        encoding="utf-8",
    )

    html = f"""
    <html>
    <head><meta charset='utf-8'><title>Download Organizer Report</title></head>
    <body>
      <h1>Download Organizer Report</h1>
      <h2>Files (top 200)</h2>{_records_df(records).head(200).to_html(index=False)}
      <h2>Move Plan (top 200)</h2>{_plan_df(plan).head(200).to_html(index=False)}
      <h2>Duplicates (top 200)</h2>{_duplicates_df(duplicates).head(200).to_html(index=False)}
    </body>
    </html>
    """
    html_path.write_text(html, encoding="utf-8")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        _records_df(records).to_excel(writer, index=False, sheet_name="files")
        _plan_df(plan).to_excel(writer, index=False, sheet_name="move_plan")
        _duplicates_df(duplicates).to_excel(writer, index=False, sheet_name="duplicates")

    return {"md": md_path, "html": html_path, "xlsx": xlsx_path}


# --------------------------------------------------------------------------- #
# Bookmark report (domain / category / duplicate URLs)
# --------------------------------------------------------------------------- #
def _bookmark_markdown(bookmarks: list[dict[str, str]], masked: bool) -> str:
    cat_counts = Counter(row.get("category", "Etc") for row in bookmarks)
    domain_counts = Counter(row.get("domain", "") for row in bookmarks)
    url_counts = Counter(row.get("url", "") for row in bookmarks)
    dup_urls = sorted({url for url, c in url_counts.items() if url and c > 1})

    lines = [
        "# Bookmark Report",
        "",
        "## Overview",
        f"- total bookmarks: {len(bookmarks)}",
        f"- query masking: {'on' if masked else 'off'}",
        "",
        "## Category Summary",
    ]
    for category, count in sorted(cat_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {category}: {count}")

    lines.extend(["", "## Domain Summary (top 30)"])
    for domain, count in sorted(domain_counts.items(), key=lambda x: (-x[1], x[0]))[:30]:
        lines.append(f"- {domain or '(empty)'}: {count}")

    lines.extend(["", "## Duplicate URLs", f"- total: {len(dup_urls)}"])
    for url in dup_urls[:50]:
        lines.append(f"- {url}")

    return "\n".join(lines)


def write_bookmark_reports(
    report_dir: Path,
    timestamp: str,
    bookmarks: list[dict[str, str]],
    masked: bool = False,
) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    base = f"bookmark_report_{timestamp}"
    md_path = report_dir / f"{base}.md"
    html_path = report_dir / f"{base}.html"
    xlsx_path = report_dir / f"{base}.xlsx"

    md_path.write_text(_bookmark_markdown(bookmarks, masked), encoding="utf-8")

    html = f"""
    <html>
    <head><meta charset='utf-8'><title>Bookmark Report</title></head>
    <body>
      <h1>Bookmark Report</h1>
      <h2>Bookmarks (top 200)</h2>{_bookmarks_df(bookmarks).head(200).to_html(index=False)}
    </body>
    </html>
    """
    html_path.write_text(html, encoding="utf-8")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        _bookmarks_df(bookmarks).to_excel(writer, index=False, sheet_name="bookmarks")

    return {"md": md_path, "html": html_path, "xlsx": xlsx_path}
