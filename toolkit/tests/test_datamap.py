import hashlib
import json
from pathlib import Path

import pytest

from genesis_toolkit import datamap as dm
from genesis_toolkit import patch as patch_mod
from tests.fixtures.make_fixture import build_fixture_rom


def _write_map(tmp_path: Path, fields: list, rom_sha256=None) -> Path:
    doc = {"game": "fixture", "fields": fields}
    if rom_sha256:
        doc["rom_sha256"] = rom_sha256
    path = tmp_path / "map.json"
    path.write_text(json.dumps(doc))
    return path


def test_reads_int_and_string_fields(tmp_path: Path):
    rom = build_fixture_rom()
    path = _write_map(tmp_path, [
        {"name": "title", "at": "0x120", "type": "str", "size": 48},
        {"name": "romend", "at": "0x1a4", "type": "u32"},
    ])
    dmap = dm.load_map(path)
    assert dm.read_field(rom, dmap.get("title")) == "GENESIS TOOLKIT TEST FIXTURE"
    assert dm.read_field(rom, dmap.get("romend")) == len(rom) - 1


def test_string_edit_writes_text_and_terminator_only(tmp_path: Path):
    # Trailing bytes in a slot are structural (length prefixes for the
    # next field), so a short string must not blank the whole slot.
    rom = build_fixture_rom()
    path = _write_map(tmp_path, [
        {"name": "title", "at": "0x120", "type": "str", "size": 48},
    ])
    dmap = dm.load_map(path)
    edits = dm.make_edits(rom, dmap, {"title": "HI"})
    assert edits[0].data == b"HI\x00"
    assert len(edits[0].expect) == len(edits[0].data)

    out = patch_mod.apply_edits(rom, edits)
    assert dm.read_field(out, dmap.get("title")) == "HI"
    # bytes past the terminator are left exactly as they were
    assert out[0x123:0x150] == rom[0x123:0x150]


def test_string_too_long_for_slot_is_rejected(tmp_path: Path):
    rom = build_fixture_rom()
    path = _write_map(tmp_path, [
        {"name": "abbr", "at": "0x120", "type": "str", "size": 4},
    ])
    dmap = dm.load_map(path)
    with pytest.raises(patch_mod.PatchError, match="slot is 4"):
        dm.make_edits(rom, dmap, {"abbr": "TOOLONG"})


def test_string_exactly_filling_slot_is_allowed(tmp_path: Path):
    rom = build_fixture_rom()
    path = _write_map(tmp_path, [
        {"name": "abbr", "at": "0x120", "type": "str", "size": 4},
    ])
    dmap = dm.load_map(path)
    assert dm.make_edits(rom, dmap, {"abbr": "ABC"})[0].data == b"ABC\x00"


def test_int_range_is_enforced(tmp_path: Path):
    rom = build_fixture_rom()
    path = _write_map(tmp_path, [{"name": "speed", "at": "0x400", "type": "u8"}])
    dmap = dm.load_map(path)
    assert dm.make_edits(rom, dmap, {"speed": "200"})[0].data == b"\xc8"
    assert dm.make_edits(rom, dmap, {"speed": "0x1f"})[0].data == b"\x1f"
    with pytest.raises(patch_mod.PatchError, match="does not fit"):
        dm.make_edits(rom, dmap, {"speed": "256"})


def test_generated_edits_carry_a_guard(tmp_path: Path):
    rom = build_fixture_rom()
    path = _write_map(tmp_path, [{"name": "speed", "at": "0x400", "type": "u8"}])
    dmap = dm.load_map(path)
    edit = dm.make_edits(rom, dmap, {"speed": "9"})[0]
    assert edit.expect == rom[0x400:0x401]
    # the guard makes the edit refuse to apply to different content
    other = bytearray(rom)
    other[0x400] ^= 0xFF
    with pytest.raises(patch_mod.PatchError, match="right revision"):
        patch_mod.apply_edits(bytes(other), [edit])


def test_rom_hash_mismatch_is_reported(tmp_path: Path):
    rom = build_fixture_rom()
    right = hashlib.sha256(rom).hexdigest()
    assert dm.check_rom_matches(dm.load_map(_write_map(
        tmp_path, [{"name": "x", "at": "0x400", "type": "u8"}], right)), rom) is None
    warning = dm.check_rom_matches(dm.load_map(_write_map(
        tmp_path, [{"name": "x", "at": "0x400", "type": "u8"}], "00" * 32)), rom)
    assert warning and "may not line up" in warning


def test_unknown_field_and_bad_map_are_errors(tmp_path: Path):
    path = _write_map(tmp_path, [{"name": "x", "at": "0x400", "type": "u8"}])
    with pytest.raises(patch_mod.PatchError, match="no field named"):
        dm.load_map(path).get("nope")

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"fields": [
        {"name": "a", "at": "0x0", "type": "u8"},
        {"name": "a", "at": "0x2", "type": "u8"},
    ]}))
    with pytest.raises(patch_mod.PatchError, match="duplicate field names"):
        dm.load_map(bad)

    worse = tmp_path / "worse.json"
    worse.write_text(json.dumps({"fields": [{"name": "a", "at": "0x0", "type": "u9"}]}))
    with pytest.raises(patch_mod.PatchError, match="unknown type"):
        dm.load_map(worse)


def test_malformed_map_raises_patcherror_not_valueerror(tmp_path: Path):
    # The CLI only catches PatchError; a bare ValueError/AttributeError
    # escaping here surfaces as a traceback.
    bad_addr = tmp_path / "a.json"
    bad_addr.write_text(json.dumps({"fields": [
        {"name": "x", "at": "0646", "type": "u8"}]}))
    with pytest.raises(patch_mod.PatchError, match="integer or hex string"):
        dm.load_map(bad_addr)

    not_object = tmp_path / "b.json"
    not_object.write_text(json.dumps({"fields": ["nope"]}))
    with pytest.raises(patch_mod.PatchError, match="must be an object"):
        dm.load_map(not_object)


def test_negative_address_is_rejected_not_wrapped(tmp_path: Path):
    # Python would slice from the end of the ROM and report plausible
    # garbage rather than failing.
    rom = build_fixture_rom()
    path = _write_map(tmp_path, [{"name": "x", "at": -4, "type": "u32"}])
    with pytest.raises(patch_mod.PatchError, match="negative address"):
        dm.read_field(rom, dm.load_map(path).get("x"))


def test_parse_assignment():
    assert dm.parse_assignment("a.b = 5") == ("a.b", "5")
    with pytest.raises(patch_mod.PatchError):
        dm.parse_assignment("nope")


def test_value_filling_its_slot_stops_at_the_next_record(tmp_path: Path):
    # A string that exactly fills its slot has no terminator, so the
    # following record's bytes sit against it. Reading those in makes an
    # untouched field look edited once a text widget normalises them.
    rom = bytearray(build_fixture_rom())
    rom[0x600:0x606] = b"Pond\x02\x01"
    path = _write_map(tmp_path, [
        {"name": "arena", "at": "0x600", "type": "str", "size": 6}])
    assert dm.read_field(bytes(rom), dm.load_map(path).get("arena")) == "Pond"
