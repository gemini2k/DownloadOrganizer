"""PyInstaller entry point for the CLI.

PyInstaller cannot run a module that uses relative imports (`from .config ...`)
as a script, so this top-level shim imports the package and calls main().
Build with build_exe.ps1.
"""
from __future__ import annotations

import sys

from download_organizer.cli import main

if __name__ == "__main__":
    sys.exit(main())
