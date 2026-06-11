from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileRecord:
    path: Path
    size: int
    modified_ts: float
    extension: str
    category: str
    duplicate_key: str
    is_old: bool


@dataclass
class MovePlanItem:
    src: Path
    dst: Path
    category: str


@dataclass
class MoveOutcome:
    history_file: Path
    moved: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)


@dataclass
class UndoOutcome:
    restored: int = 0
    skipped: list[dict[str, str]] = field(default_factory=list)


@dataclass
class UndoPreview:
    """What an undo WOULD do, without moving anything."""

    restorable: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


@dataclass
class CleanPlanItem:
    """A file proposed for the Recycle Bin (never permanently deleted)."""

    path: Path
    reason: str  # "duplicate" | "old" | "selected"
    size: int


@dataclass
class TrashOutcome:
    history_file: Path
    trashed: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
