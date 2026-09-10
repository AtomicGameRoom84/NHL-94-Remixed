"""Named fields in a ROM: the layer that makes editing legible.

A *data map* is a JSON file that gives names, addresses and types to
interesting bytes in a particular game -- the equivalent of the ROM maps
romhacking communities have always traded, in a form the toolkit can
read:

    {
      "game": "Some Game (USA)",
      "rom_sha256": "abc123...",
      "fields": [
        {"name": "team.BOS.city", "at": "0xc28", "type": "str", "size": 8},
        {"name": "rules.period_minutes", "at": "0x1234", "type": "u8"}
      ]
    }

The map holds *addresses*, never the values found there, so it stays a
description of layout rather than a copy of the game's content.

`rom_sha256` records which image the addresses were derived from. Maps
get traded between people running different revisions, and an address
that's right for one dump is meaningless in another, so reading a map
against a ROM whose hash doesn't match warns rather than silently
reporting whatever happens to be at that offset.

Edits produced here route through the same patch layer as everything
else, with `expect` auto-filled from the bytes currently present -- so a
generated mod is guarded by construction.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .patch import Edit, PatchError, _parse_int

INT_TYPES = {"u8": 1, "u16": 2, "u32": 4}


@dataclass
class Field:
    name: str
    address: int
    type: str
    size: int
    note: str

    @property
    def end(self) -> int:
        return self.address + self.size


@dataclass
class DataMap:
    game: str
    rom_sha256: str | None
    fields: list[Field]

    def get(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise PatchError(f"no field named {name!r} in this map")


def load_map(path: Path) -> DataMap:
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise PatchError(
            f"no such map file: {path}. Map paths in the docs are relative to "
            f"the toolkit directory -- either run from there, or give a full path."
        ) from None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise PatchError(f"{path}: invalid JSON ({e})") from e
    if not isinstance(doc, dict) or not isinstance(doc.get("fields"), list):
        raise PatchError(f"{path}: needs a \"fields\" list")

    fields = []
    for i, raw in enumerate(doc["fields"]):
        where = f"{path}: fields[{i}]"
        if not isinstance(raw, dict):
            raise PatchError(f"{where}: must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise PatchError(f"{where}: needs a name")
        ftype = raw.get("type")
        # Shares patch.py's parser so a malformed address raises
        # PatchError like every other input problem, rather than a bare
        # ValueError escaping the CLI's error handling.
        address = _parse_int(raw.get("at"), f"{where}.at")

        if ftype in INT_TYPES:
            size = INT_TYPES[ftype]
        elif ftype == "str":
            size = raw.get("size")
            if not isinstance(size, int) or size < 1:
                raise PatchError(f"{where}: str fields need a positive \"size\"")
        else:
            raise PatchError(
                f"{where}: unknown type {ftype!r} "
                f"(expected one of {', '.join(sorted(INT_TYPES))}, str)"
            )
        fields.append(Field(name=name, address=address, type=ftype,
                            size=size, note=str(raw.get("note", ""))))

    names = [f.name for f in fields]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise PatchError(f"{path}: duplicate field names: {', '.join(sorted(dupes))}")

    return DataMap(game=str(doc.get("game", path.stem)),
                   rom_sha256=doc.get("rom_sha256"), fields=fields)


def check_rom_matches(dmap: DataMap, rom: bytes) -> str | None:
    """Return a warning if the ROM isn't the one the map was built from."""
    if not dmap.rom_sha256:
        return None
    actual = hashlib.sha256(rom).hexdigest()
    if actual.lower() != dmap.rom_sha256.lower():
        return (f"this map was built for a ROM with sha256 {dmap.rom_sha256[:16]}... "
                f"but this one is {actual[:16]}...; addresses may not line up")
    return None


def read_field(rom: bytes, field: Field):
    if field.address < 0:
        raise PatchError(f"field {field.name!r} has a negative address "
                         f"({field.address}); Python would slice from the end "
                         f"of the ROM and report plausible-looking garbage")
    if field.end > len(rom):
        raise PatchError(f"field {field.name!r} at 0x{field.address:06x} is past "
                         f"the end of the ROM")
    raw = rom[field.address:field.end]
    if field.type == "str":
        # Two padding conventions coexist in a Genesis ROM: the
        # cartridge header space-pads its fields, while in-game string
        # tables NUL-terminate. Handle both so a map can describe
        # either without the caller caring which.
        #
        # Stop at the first control byte as well, not just NUL. A string
        # that exactly fills its slot has no terminator, so the next
        # record's bytes sit right against it -- and a value carrying a
        # stray control character round-trips badly through anything
        # that normalises text (a GUI entry box drops it, then reports
        # an untouched field as edited).
        text = raw.split(b"\x00")[0]
        cut = next((i for i, b in enumerate(text) if b < 0x20), len(text))
        return text[:cut].decode("latin1").rstrip()
    return int.from_bytes(raw, "big")


def encode_field(field: Field, value) -> bytes:
    """Turn a user-supplied value into the exact bytes for this field."""
    if field.type == "str":
        text = value if isinstance(value, str) else str(value)
        encoded = text.encode("latin1", errors="replace")
        # Always leave room for the terminator: these strings sit in
        # fixed slots, and running past one would overwrite the next
        # field rather than just truncating the text.
        if len(encoded) + 1 > field.size:
            raise PatchError(
                f"{field.name}: {text!r} needs {len(encoded) + 1} bytes "
                f"(including a terminator) but the slot is {field.size}"
            )
        # Write the text and its terminator only -- deliberately not
        # padding out the rest of the slot. Trailing bytes in these
        # slots are structural (length prefixes for the following
        # field, alignment padding), and blanking them would corrupt
        # the record even though the text itself looked fine.
        return encoded + b"\x00"

    if isinstance(value, str):
        try:
            number = int(value, 0)
        except ValueError:
            raise PatchError(f"{field.name}: {value!r} is not a number") from None
    else:
        number = int(value)

    limit = 1 << (field.size * 8)
    if not 0 <= number < limit:
        raise PatchError(f"{field.name}: {number} does not fit in {field.type} "
                         f"(0..{limit - 1})")
    return number.to_bytes(field.size, "big")


def make_edits(rom: bytes, dmap: DataMap, assignments: dict[str, str]) -> list[Edit]:
    """Build guarded edits for `name=value` assignments."""
    edits = []
    for name, value in assignments.items():
        field = dmap.get(name)
        if field.end > len(rom):
            raise PatchError(f"field {name!r} is past the end of the ROM")
        data = encode_field(field, value)
        # Guard exactly the span being written -- a string edit is
        # usually shorter than its slot, and expecting the whole slot
        # would both over-constrain the guard and imply we overwrite
        # bytes we deliberately leave alone.
        edits.append(Edit(address=field.address, data=data,
                          expect=rom[field.address:field.address + len(data)],
                          note=f"{name} = {value}"))
    return edits


def parse_assignment(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise PatchError(f"expected NAME=VALUE, got {text!r}")
    name, _, value = text.partition("=")
    return name.strip(), value.strip()
