"""PyInstaller entry point.

PyInstaller needs a real script to start from; the console_scripts entry
point in pyproject.toml isn't something it can target directly. This is
that script, kept in the repo so the frozen build is reproducible rather
than depending on a file someone typed once on a build machine.
"""
import sys

from genesis_toolkit.cli import main

if __name__ == "__main__":
    sys.exit(main())
