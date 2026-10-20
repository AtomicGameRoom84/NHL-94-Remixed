#!/usr/bin/env python3
"""Assemble src/nhl94.asm into a cartridge image."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / "tools" / "toolchain-lock.json").read_text())


class BuildError(Exception):
    pass


def find_assembler() -> Path:
    """Prefer the pinned local build, then anything on PATH."""
    name = LOCK["vasm"]["binary"]
    local = ROOT / ".local" / "vasm" / name
    if local.is_file() and os.access(local, os.X_OK):
        return local
    found = shutil.which(name)
    if found:
        return Path(found)
    raise BuildError(
        f"{name} not found. Run tools/setup.py to fetch and build the pinned "
        f"version ({LOCK['vasm']['version']}), or put it on your PATH."
    )


def assemble(asm: Path, out: Path, assembler: Path | None = None,
             include_dir: Path | None = None) -> Path:
    assembler = assembler or find_assembler()
    out.parent.mkdir(parents=True, exist_ok=True)
    # -no-opt is not a preference. See the note in src/nhl94.asm.
    # -I points at the generated regions.inc, so the build does not
    # depend on which directory it is invoked from.
    cmd = [str(assembler), "-m68000", "-Fbin", "-no-opt", "-quiet"]
    if include_dir:
        cmd += ["-I", str(include_dir.resolve())]
    cmd += ["-o", str(out), str(asm)]
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0 or not out.is_file():
        raise BuildError(
            "assembly failed:\n"
            + (done.stdout + done.stderr).strip()
            + f"\n\ncommand: {' '.join(cmd)}"
        )
    # vasm reports some problems on stdout while still exiting 0.
    noise = (done.stdout + done.stderr).strip()
    if noise:
        print(noise, file=sys.stderr)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asm", default=str(ROOT / "src" / "nhl94.asm"))
    p.add_argument("--out", default=str(ROOT / "build" / "nhl94.bin"))
    p.add_argument("--assembler")
    p.add_argument("--include-dir", default=str(ROOT / "build"))
    a = p.parse_args()
    try:
        out = assemble(Path(a.asm), Path(a.out),
                       Path(a.assembler) if a.assembler else None,
                       Path(a.include_dir))
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
