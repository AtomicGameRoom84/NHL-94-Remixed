"""Identify a cartridge dump by content, never by filename.

A ROM hack that silently half-applies to the wrong revision is the
classic way this kind of project wastes someone's afternoon, so every
tool here refuses to touch a dump it cannot name. An unrecognised dump
is reported with its own digests, which is all anyone needs to add it to
tools/rom-lock.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = ROOT / "tools" / "rom-lock.json"


class RomError(Exception):
    """The supplied file is not a cartridge this project can build."""


def _display(path: Path) -> str:
    """Repo-relative where possible, absolute otherwise.

    A lock file is allowed to live anywhere -- a user supporting their
    own ROM revision, or a test using a temporary one -- so this must not
    assume it sits inside the project. relative_to() raises on anything
    outside, which would replace the useful "unknown cartridge" message
    with a ValueError traceback.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def digests(data: bytes) -> dict[str, str]:
    return {"sha1": hashlib.sha1(data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest()}


def identify(rom_path: Path, lock_path: Path = DEFAULT_LOCK) -> dict:
    """Return the rom-lock entry describing `rom_path`."""
    if not rom_path.is_file():
        raise RomError(
            f"no cartridge at {rom_path}\n"
            f"Put your own dump in {ROOT / 'rom'} -- see its DROP-ROM-HERE.txt."
        )
    data = rom_path.read_bytes()
    found = digests(data)
    revisions = json.loads(lock_path.read_text())["revisions"]

    for entry in revisions:
        # Compare only the digests the lock actually pins. An entry that
        # records sha1 alone still identifies a ROM; treating its null
        # sha256 as a value to match would reject every real cartridge.
        pinned = {k: entry[k] for k in ("sha1", "sha256") if entry.get(k)}
        if pinned and all(found[k] == v for k, v in pinned.items()):
            if entry["size"] != len(data):
                raise RomError(
                    f"{rom_path.name} matches {entry['id']} by hash but is "
                    f"{len(data):,} bytes, not {entry['size']:,}. "
                    f"The lock file is inconsistent."
                )
            return entry

    known = ", ".join(e["id"] for e in revisions) or "(none)"
    raise RomError(
        f"{rom_path.name} is not a revision this project knows.\n"
        f"  size   : {len(data):,} bytes\n"
        f"  sha1   : {found['sha1']}\n"
        f"  sha256 : {found['sha256']}\n"
        f"  known  : {known}\n"
        f"If this is a good dump of a revision you want supported, add the "
        f"digests above to {_display(lock_path)} as a new entry."
    )
