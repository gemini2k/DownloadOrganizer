from __future__ import annotations

from pathlib import Path

from .config import blocked_roots


def ensure_safe_scan_root(scan_root: Path) -> None:
    resolved = scan_root.resolve()
    for blocked in blocked_roots():
        try:
            blocked_resolved = blocked.resolve()
        except OSError:
            continue
        if resolved == blocked_resolved or blocked_resolved in resolved.parents:
            raise ValueError(f"Blocked system path: {resolved}")


def is_within(child: Path, parent: Path) -> bool:
    """True if `child` is `parent` itself or lives somewhere under it."""
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
    except OSError:
        return False
    return child_resolved == parent_resolved or parent_resolved in child_resolved.parents


def ensure_source_within_scan_root(source: Path, scan_root: Path) -> None:
    """Hard guard: a move source MUST live inside the selected download folder.

    This is the last line of defence behind the user rule
    "never touch anything outside the download folder".
    """
    if not is_within(source, scan_root):
        raise ValueError(f"Refusing to touch a file outside the scan folder: {source}")
