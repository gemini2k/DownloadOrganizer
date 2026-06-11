# pyright: reportMissingTypeArgument=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from .config import categorize_bookmark


def mask_url_query(url: str) -> str:
    """Drop querystring + fragment (and params) so reports don't leak tokens/IDs."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _bookmark_paths() -> list[tuple[str, Path]]:
    local = Path.home() / "AppData" / "Local"
    return [
        ("chrome", local / "Google" / "Chrome" / "User Data" / "Default" / "Bookmarks"),
        ("edge", local / "Microsoft" / "Edge" / "User Data" / "Default" / "Bookmarks"),
    ]


def _walk_nodes(
    nodes: list[dict],
    folder_chain: list[str],
    browser: str,
    mask_query: bool,
    exclude_domains: list[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for node in nodes:
        node_type = node.get("type", "")
        name = str(node.get("name", ""))
        if node_type == "folder":
            children = node.get("children", []) or []
            rows.extend(_walk_nodes(children, folder_chain + [name], browser, mask_query, exclude_domains))
        elif node_type == "url":
            url = str(node.get("url", ""))
            host = urlparse(url).netloc
            if any(blocked.lower() in host.lower() for blocked in exclude_domains if blocked.strip()):
                continue
            if mask_query:
                url = mask_url_query(url)
            rows.append(
                {
                    "browser": browser,
                    "folder": " / ".join(folder_chain),
                    "name": name,
                    "url": url,
                    "domain": host,
                    "category": categorize_bookmark(host, name, url),
                }
            )
    return rows


def analyze_bookmarks(
    mask_query: bool = False, exclude_domains: list[str] | None = None
) -> list[dict[str, str]]:
    exclude = exclude_domains or []
    rows: list[dict[str, str]] = []
    for browser, path in _bookmark_paths():
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        roots = (data.get("roots") or {}).values()
        for root in roots:
            children = root.get("children", []) if isinstance(root, dict) else []
            rows.extend(
                _walk_nodes(children, [str(root.get("name", "root"))], browser, mask_query, exclude)
            )
    return rows


def duplicate_urls(bookmarks: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return bookmark rows whose URL appears more than once (kept for user review only)."""
    counts: dict[str, int] = {}
    for row in bookmarks:
        url = row.get("url", "")
        counts[url] = counts.get(url, 0) + 1
    return [row for row in bookmarks if counts.get(row.get("url", ""), 0) > 1]
