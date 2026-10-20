#!/usr/bin/env python3
"""Refuse to commit what this project says it will not publish.

ASSET_AUDIT.md promises no cartridge-derived data, and FIDELITY.md
requires every region to carry a name and its evidence. Both are just
prose until something enforces them, so this is the enforcement.

The secret and decompiler-output patterns are adapted from
universal-modder's `um publish check` (MIT, rehan-remade/universal-modder),
with three changes that matter for a Genesis disassembly:

- It inspects **tracked files only**, via `git ls-files`. The original
  walks the working tree, which on this project means 223 files of
  fetched vasm toolchain in `.local/` and zero of our own assembly --
  a pass that says nothing about what we actually publish.
- It knows about **assembly**. `.asm`, `.s` and `.inc` are in neither of
  the original's extension sets, so the file type this entire project
  consists of was never opened.
- Its decompiler-name check is **case-insensitive**. IDA emits
  `sub_117AC`; this project's own tracer emits `sub_0117b2`. Catching
  only the uppercase form would miss ours.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = [
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI key", re.compile(r"\bsk-(?:(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{32,}|[A-Za-z0-9]{32,})")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,})")),
    ("AWS key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

# A raw decompiler label is machine output with no claim attached. A
# region named sub_0117b2 has not been understood -- it has been
# located -- and committing it as code quietly defeats the requirement
# that every region carry a real name and its evidence.
AUTO_NAME = re.compile(
    r"\b(?:FUN|DAT|LAB|PTR)_[0-9a-fA-F]{6,}\b"
    r"|\b(?:sub|loc|unk|off|dword|qword)_[0-9a-fA-F]{5,}\b")
DECOMPILER_HEADER = re.compile(
    r"^\s*(?://|#|--|;)\s*(?:Decompiled with|Decompiler:|ILSpy|dnSpy|JetBrains decompiler)",
    re.I | re.M)

# Anything carved from, or built out of, the cartridge.
CARTRIDGE_SUFFIXES = {".bin", ".gen", ".smd", ".32x", ".68k", ".ips", ".inc"}
TEXT_SUFFIXES = {".asm", ".s", ".inc", ".py", ".md", ".json", ".yml", ".yaml",
                 ".txt", ".cfg", ".toml", ".sh", ".bat", ".ps1"}
# Assembly and notes are where a pasted decompiler dump would land.
CODE_SUFFIXES = {".asm", ".s", ".inc"}

USER_PATH = re.compile(r"[A-Z]:\\Users\\[^\\\s\"']+|/home/[a-z_][a-z0-9_-]*/|/Users/[A-Za-z]+/")


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [ROOT / name for name in out.stdout.split("\0") if name]


def check() -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []

    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            continue

        if path.suffix.lower() in CARTRIDGE_SUFFIXES:
            fails.append(f"cartridge-derived file is tracked: {rel}")
            continue
        if rel.startswith("rom/") and path.name != "DROP-ROM-HERE.txt":
            fails.append(f"only instructions belong in rom/: {rel}")
            continue
        if path.name == ".env" or path.name.endswith(".env"):
            fails.append(f"env file (secrets?): {rel}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue

        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue

        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                fails.append(f"{label} in {rel}")

        if path.suffix.lower() in CODE_SUFFIXES:
            # Documentation may cite someone else's published label --
            # that is how a finding stays checkable. Committed assembly
            # may not: see FIDELITY.md.
            found = AUTO_NAME.findall(text)
            if found:
                fails.append(
                    f"raw decompiler name x{len(found)} in {rel} "
                    f"(e.g. {found[0]!r}) -- name the routine and record "
                    f"its evidence, per docs/FIDELITY.md")
            if DECOMPILER_HEADER.search(text):
                fails.append(f"decompiler output header in {rel}")

        if USER_PATH.search(text):
            warns.append(f"absolute user path in {rel}")

    return fails, warns


def main() -> int:
    fails, warns = check()
    for w in warns:
        print(f"warn: {w}")
    for f in fails:
        print(f"FAIL: {f}")
    tracked = len(tracked_files())
    if fails:
        print(f"\n{len(fails)} failure(s) across {tracked} tracked files.")
        return 1
    print(f"PASS: {tracked} tracked files, 0 failures, {len(warns)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
