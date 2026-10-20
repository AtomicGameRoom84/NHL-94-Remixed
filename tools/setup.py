#!/usr/bin/env python3
"""Fetch and build the pinned assembler. Downloads nothing unverified.

The toolchain is pinned by SHA-256 rather than vendored, so this repo
carries no third-party binaries and a substituted tarball stops the
build instead of quietly changing the ROM it produces.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
LOCK = json.loads((ROOT / "tools" / "toolchain-lock.json").read_text())


class SetupError(Exception):
    pass


def download(entry: dict) -> Path:
    LOCAL.mkdir(exist_ok=True)
    target = LOCAL / entry["filename"]
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]:
        return target
    print(f"Downloading pinned {entry['filename']} ({entry['version']})", flush=True)
    request = urllib.request.Request(entry["url"],
                                     headers={"User-Agent": "nhl94-disasm-setup"})
    with urllib.request.urlopen(request, timeout=120) as response:
        blob = response.read()
    got = hashlib.sha256(blob).hexdigest()
    if got != entry["sha256"]:
        raise SetupError(
            f"checksum mismatch for {entry['filename']}\n"
            f"  expected {entry['sha256']}\n  got      {got}\n"
            f"Refusing to build with it."
        )
    target.write_bytes(blob)
    return target


def unpack(archive: Path, destination: Path) -> None:
    """Extract without trusting any path or link inside the archive."""
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()

    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if "\\" in member.name or ":" in member.name:
                raise SetupError(f"unsafe archive member: {member.name}")
            if not (base / member.name).resolve().is_relative_to(base):
                raise SetupError(f"archive path escapes setup directory: {member.name}")
            if member.issym() or member.islnk():
                raise SetupError(f"archive link refused: {member.name}")
        tar.extractall(destination, filter="data")


def build_vasm() -> Path:
    entry = LOCK["vasm"]
    out = LOCAL / "vasm" / entry["binary"]
    if out.is_file():
        print(f"Assembler already built: {out}")
        return out

    unpack(download(entry), LOCAL / "vasm-src")
    source = next((LOCAL / "vasm-src").glob("vasm*"), None)
    if source is None or not (source / "Makefile").is_file():
        raise SetupError("unpacked archive does not look like a vasm source tree")

    print("Building vasmm68k_mot", flush=True)
    done = subprocess.run(["make", "CPU=m68k", "SYNTAX=mot"],
                          cwd=source, capture_output=True, text=True)
    built = source / entry["binary"]
    if done.returncode != 0 or not built.is_file():
        raise SetupError("vasm build failed:\n" + (done.stdout + done.stderr)[-2000:])

    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, out)
    print(f"Assembler ready: {out}")
    return out


def main() -> int:
    if sys.version_info < (3, 11):
        print("error: Python 3.11+ is required", file=sys.stderr)
        return 1
    try:
        build_vasm()
    except (SetupError, OSError) as e:
        print(f"\nSetup failed: {e}", file=sys.stderr)
        return 1
    print("\nSetup complete. Put your cartridge in rom/ and run tools/verify.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
