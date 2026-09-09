"""Declarative ROM patching: a mod is a JSON file, not a modified ROM.

The point of keeping mods as patches rather than edited ROM images is
that a patch is small, diffable, reviewable, version-controllable, and
carries no copyrighted content -- so it can live in a git repo next to
the disassembly while the ROM never does.

A mod file looks like:

    {
      "name": "faster-skating",
      "notes": "bump the base skater speed constant",
      "edits": [
        {"at": "0x7ac6", "asm": "moveq #5, d0", "expect": "7003",
         "note": "was moveq #3"},
        {"at": "0x9120", "bytes": "4e714e71", "note": "nop out the check"}
      ]
    }

Each edit names an address and either `asm` (assembled in place, at its
real address, so PC-relative operands resolve correctly) or `bytes`
(raw hex). The optional `expect` field is the important one: it records
the bytes the edit assumes are already there, and applying refuses if
they don't match. That turns "this mod was written against a different
ROM revision" from silent corruption -- the failure mode that makes
ROM patches infamous -- into a clear error naming the address.

Edits may never change the ROM's length; a Genesis cartridge is a fixed
address space, so patching is always in-place overwriting.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .build import assemble_at
from .header import compute_checksum


class PatchError(RuntimeError):
    pass


@dataclass
class Edit:
    address: int
    data: bytes
    expect: bytes | None
    note: str

    @property
    def end(self) -> int:
        return self.address + len(self.data)


def _parse_int(value, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise PatchError(f"{field}: expected an integer or hex string, got {value!r}")


def _parse_hex_bytes(value, field: str) -> bytes:
    if not isinstance(value, str):
        raise PatchError(f"{field}: expected a hex string, got {value!r}")
    text = value.replace(" ", "").replace("_", "")
    try:
        return bytes.fromhex(text)
    except ValueError as e:
        raise PatchError(f"{field}: not valid hex ({e})") from e


def load_mod(path: Path) -> tuple[str, list[Edit]]:
    """Read a mod file, assembling any `asm` edits so every edit comes
    back as concrete bytes."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise PatchError(f"no such mod file: {path}") from None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise PatchError(f"{path}: invalid JSON ({e})") from e
    if not isinstance(doc, dict):
        raise PatchError(f"{path}: top level must be an object")

    name = doc.get("name") or path.stem
    raw_edits = doc.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        raise PatchError(f"{path}: needs a non-empty \"edits\" list")

    edits: list[Edit] = []
    for i, raw in enumerate(raw_edits):
        where = f"{path}: edits[{i}]"
        if not isinstance(raw, dict):
            raise PatchError(f"{where}: must be an object")
        if ("asm" in raw) == ("bytes" in raw):
            raise PatchError(f"{where}: needs exactly one of \"asm\" or \"bytes\"")

        address = _parse_int(raw.get("at"), f"{where}.at")
        if "asm" in raw:
            source = raw["asm"]
            if not isinstance(source, str):
                raise PatchError(f"{where}.asm: expected a string")
            data = assemble_at(source, address)
        else:
            data = _parse_hex_bytes(raw["bytes"], f"{where}.bytes")
        if not data:
            raise PatchError(f"{where}: assembled to zero bytes")

        expect = (_parse_hex_bytes(raw["expect"], f"{where}.expect")
                  if "expect" in raw else None)
        if expect is not None and len(expect) != len(data):
            raise PatchError(
                f"{where}: \"expect\" is {len(expect)} bytes but the edit "
                f"writes {len(data)}; they must describe the same span"
            )
        edits.append(Edit(address=address, data=data, expect=expect,
                          note=str(raw.get("note", ""))))
    return name, edits


def apply_edits(rom: bytes, edits: list[Edit], *, fix_checksum: bool = True) -> bytes:
    """Apply edits to a ROM image, returning the patched image.

    Raises PatchError on anything suspicious rather than producing a
    subtly broken ROM: an edit running past the end of the cartridge, an
    `expect` guard that doesn't match, or two edits touching the same
    bytes (which would make the result depend on ordering).
    """
    out = bytearray(rom)
    claimed: list[Edit] = []

    for edit in edits:
        if edit.address < 0 or edit.end > len(out):
            raise PatchError(
                f"edit at 0x{edit.address:06x} ({len(edit.data)} bytes) runs past "
                f"the end of the {len(out)}-byte ROM; edits cannot resize a cartridge"
            )
        for other in claimed:
            if edit.address < other.end and other.address < edit.end:
                raise PatchError(
                    f"edits at 0x{edit.address:06x} and 0x{other.address:06x} overlap; "
                    f"the result would depend on which ran first"
                )
        if edit.expect is not None:
            found = bytes(out[edit.address:edit.end])
            if found != edit.expect:
                raise PatchError(
                    f"edit at 0x{edit.address:06x}: expected {edit.expect.hex()} "
                    f"but found {found.hex()}. This mod was written against "
                    f"different ROM contents -- check you have the right revision."
                )
        out[edit.address:edit.end] = edit.data
        claimed.append(edit)

    if fix_checksum:
        return fix_header_checksum(bytes(out))
    return bytes(out)


def fix_header_checksum(rom: bytes) -> bytes:
    """Recompute the header checksum at 0x18E to match the ROM body.

    Most emulators ignore this field, but some games self-check it and
    some tools flag a mismatch as a bad dump, so a patched ROM should
    carry a correct one.
    """
    if len(rom) < 0x200:
        return rom
    out = bytearray(rom)
    out[0x18E:0x190] = compute_checksum(bytes(out)).to_bytes(2, "big")
    return bytes(out)


# --- IPS -------------------------------------------------------------
#
# IPS is the lowest common denominator of ROM patch formats: every
# emulator front end and patcher reads it. Records are a 3-byte
# big-endian offset and a 2-byte big-endian length, or -- when the
# length is zero -- a run-length record of a 2-byte count and one
# repeated byte. The format tops out at a 16 MiB offset, which no
# Genesis cartridge reaches.

IPS_MAGIC = b"PATCH"
IPS_EOF = b"EOF"
_IPS_MAX_OFFSET = 0xFFFFFF
_IPS_MAX_CHUNK = 0xFFFF
# "EOF" read as a 3-byte offset. A record can't start here or a patcher
# would stop reading, so such a run is nudged one byte earlier.
_EOF_OFFSET = 0x454F46


def _diff_runs(original: bytes, modified: bytes):
    """Yield (offset, length) spans where the two images differ."""
    i = 0
    n = len(modified)
    while i < n:
        if i < len(original) and original[i] == modified[i]:
            i += 1
            continue
        start = i
        while i < n and (i >= len(original) or original[i] != modified[i]):
            i += 1
        yield start, i - start


def create_ips(original: bytes, modified: bytes) -> bytes:
    """Build an IPS patch turning `original` into `modified`."""
    if len(modified) < len(original):
        raise PatchError("IPS cannot represent a ROM that got shorter")
    if len(modified) > _IPS_MAX_OFFSET + 1:
        raise PatchError("ROM is too large for the IPS format (16 MiB limit)")

    out = bytearray(IPS_MAGIC)
    for offset, length in _diff_runs(original, modified):
        while length > 0:
            if offset == _EOF_OFFSET:
                # A record whose 3-byte offset is literally "EOF" ends
                # the patch early, silently dropping everything after
                # it. Start one byte sooner instead; that byte gets
                # rewritten with the value it already has.
                #
                # This has to be checked per chunk rather than once per
                # run: the 0xFFFF chunk split below can land a *later*
                # record exactly on the offset even when the run began
                # nowhere near it.
                offset -= 1
                length += 1
            chunk = min(length, _IPS_MAX_CHUNK)
            out += offset.to_bytes(3, "big")
            out += chunk.to_bytes(2, "big")
            out += modified[offset:offset + chunk]
            offset += chunk
            length -= chunk
    out += IPS_EOF
    return bytes(out)


def apply_ips(rom: bytes, patch: bytes) -> bytes:
    """Apply an IPS patch to a ROM image."""
    if not patch.startswith(IPS_MAGIC):
        raise PatchError("not an IPS patch (missing \"PATCH\" magic)")

    out = bytearray(rom)
    pos = len(IPS_MAGIC)
    while True:
        if pos + 3 > len(patch):
            raise PatchError("IPS patch ended without an EOF marker")
        if patch[pos:pos + 3] == IPS_EOF:
            break
        offset = int.from_bytes(patch[pos:pos + 3], "big")
        pos += 3
        if pos + 2 > len(patch):
            raise PatchError("truncated IPS record header")
        size = int.from_bytes(patch[pos:pos + 2], "big")
        pos += 2

        if size == 0:  # run-length record
            if pos + 3 > len(patch):
                raise PatchError("truncated IPS run-length record")
            count = int.from_bytes(patch[pos:pos + 2], "big")
            value = patch[pos + 2]
            pos += 3
            data = bytes([value]) * count
        else:
            if pos + size > len(patch):
                raise PatchError("truncated IPS data record")
            data = patch[pos:pos + size]
            pos += size

        if offset + len(data) > len(out):
            out.extend(b"\x00" * (offset + len(data) - len(out)))
        out[offset:offset + len(data)] = data
    return bytes(out)
