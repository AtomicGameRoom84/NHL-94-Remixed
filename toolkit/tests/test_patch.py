import json
import shutil
from pathlib import Path

import pytest

from genesis_toolkit import build as build_mod
from genesis_toolkit import patch as patch_mod
from genesis_toolkit.header import parse_header
from tests.fixtures.make_fixture import build_fixture_rom


def _has_m68k_as() -> bool:
    return shutil.which(build_mod.AS) is not None


def _write_mod(tmp_path: Path, edits: list) -> Path:
    path = tmp_path / "mod.json"
    path.write_text(json.dumps({"name": "test-mod", "edits": edits}))
    return path


def test_byte_edit_applies(tmp_path: Path):
    rom = build_fixture_rom()
    mod = _write_mod(tmp_path, [{"at": "0x400", "bytes": "4e71"}])
    _, edits = patch_mod.load_mod(mod)
    out = patch_mod.apply_edits(rom, edits)
    assert out[0x400:0x402] == bytes.fromhex("4e71")
    assert len(out) == len(rom)


def test_expect_guard_rejects_wrong_rom(tmp_path: Path):
    rom = build_fixture_rom()
    mod = _write_mod(tmp_path, [
        {"at": "0x400", "bytes": "4e71", "expect": "dead"},
    ])
    _, edits = patch_mod.load_mod(mod)
    with pytest.raises(patch_mod.PatchError, match="right revision"):
        patch_mod.apply_edits(rom, edits)


def test_expect_guard_accepts_matching_bytes(tmp_path: Path):
    rom = build_fixture_rom()
    original = rom[0x400:0x402].hex()
    mod = _write_mod(tmp_path, [
        {"at": "0x400", "bytes": "4e71", "expect": original},
    ])
    _, edits = patch_mod.load_mod(mod)
    assert patch_mod.apply_edits(rom, edits)[0x400:0x402] == bytes.fromhex("4e71")


def test_edit_past_end_of_rom_is_rejected(tmp_path: Path):
    rom = build_fixture_rom()
    mod = _write_mod(tmp_path, [{"at": hex(len(rom) - 1), "bytes": "4e71"}])
    _, edits = patch_mod.load_mod(mod)
    with pytest.raises(patch_mod.PatchError, match="past the end"):
        patch_mod.apply_edits(rom, edits)


def test_overlapping_edits_are_rejected(tmp_path: Path):
    rom = build_fixture_rom()
    mod = _write_mod(tmp_path, [
        {"at": "0x400", "bytes": "4e714e71"},
        {"at": "0x402", "bytes": "4e75"},
    ])
    _, edits = patch_mod.load_mod(mod)
    with pytest.raises(patch_mod.PatchError, match="overlap"):
        patch_mod.apply_edits(rom, edits)


def test_expect_length_must_match_edit_length(tmp_path: Path):
    mod = _write_mod(tmp_path, [
        {"at": "0x400", "bytes": "4e71", "expect": "4e7100"},
    ])
    with pytest.raises(patch_mod.PatchError, match="same span"):
        patch_mod.load_mod(mod)


def test_edit_needs_exactly_one_of_asm_or_bytes(tmp_path: Path):
    mod = _write_mod(tmp_path, [{"at": "0x400"}])
    with pytest.raises(patch_mod.PatchError, match="exactly one"):
        patch_mod.load_mod(mod)


def test_patching_fixes_the_checksum(tmp_path: Path):
    rom = build_fixture_rom()
    assert parse_header(rom).checksum_ok
    mod = _write_mod(tmp_path, [{"at": "0x500", "bytes": "ffff"}])
    _, edits = patch_mod.load_mod(mod)

    unfixed = patch_mod.apply_edits(rom, edits, fix_checksum=False)
    assert not parse_header(unfixed).checksum_ok

    fixed = patch_mod.apply_edits(rom, edits)
    assert parse_header(fixed).checksum_ok


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_asm_edit_assembles_at_its_real_address(tmp_path: Path):
    # A branch must encode a displacement relative to where the edit
    # actually lands, not relative to zero.
    rom = build_fixture_rom()
    mod = _write_mod(tmp_path, [{"at": "0x400", "asm": "\tbra.w rom+0x420"}])
    _, edits = patch_mod.load_mod(mod)
    out = patch_mod.apply_edits(rom, edits)
    # bra.w displacement is measured from the address after the opcode
    # word: 0x420 - (0x400 + 2) = 0x1e.
    assert out[0x400:0x404] == bytes.fromhex("6000001e")


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_assemble_at_is_position_dependent():
    # Same absolute target, two different edit sites -> different
    # displacements. If these matched, the operand wasn't being
    # resolved against the edit's real address.
    at_400 = build_mod.assemble_at("\tbra.w rom+0x420", 0x400)
    at_800 = build_mod.assemble_at("\tbra.w rom+0x420", 0x800)
    assert at_400 != at_800


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_here_label_is_relative_to_the_edit_site():
    # here+0x20 from 0x400 targets 0x420: displacement 0x420-0x402.
    assert build_mod.assemble_at("\tbra.w here+0x20", 0x400) == bytes.fromhex("6000001e")


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_bare_branch_target_is_rejected_not_silently_zeroed():
    # GNU as encodes `bra.w 0x420` as a zero displacement with no
    # diagnostic. That must be caught, not passed through.
    with pytest.raises(build_mod.AssembleError, match="silently encode the wrong target"):
        build_mod.assemble_at("\tbra.w 0x420", 0x400)


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_dbcc_bare_target_is_rejected():
    # DBcc puts its counter register first, so a guard that inspects the
    # first operand sees "d0" and lets the real target through.
    # `dbra d0, 0x420` assembles to a zero displacement: an infinite loop.
    with pytest.raises(build_mod.AssembleError, match="silently encode the wrong target"):
        build_mod.assemble_at("\tdbra d0, 0x420", 0x400)
    assert build_mod.assemble_at("\tdbra d0, rom+0x420", 0x400) == bytes.fromhex("51c8001e")


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_label_on_the_same_line_does_not_bypass_the_guard():
    with pytest.raises(build_mod.AssembleError, match="silently encode the wrong target"):
        build_mod.assemble_at("spot: bra.w 0x420", 0x400)


def test_ips_record_never_starts_on_the_eof_offset():
    # A record whose 3-byte offset is literally "EOF" truncates the
    # patch. The 0xFFFF chunk split can land a *later* record there even
    # when the run started nowhere near it.
    eof = patch_mod._EOF_OFFSET
    original = bytes(eof + 0x200)
    for start in (eof - patch_mod._IPS_MAX_CHUNK, eof):
        modified = bytearray(original)
        for i in range(start, eof + 0x100):
            modified[i] = 0xAB
        modified = bytes(modified)
        ips = patch_mod.create_ips(original, modified)
        assert patch_mod.apply_ips(original, ips) == modified, f"run from 0x{start:x}"


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_non_pcrel_bare_address_is_still_allowed():
    # jsr uses absolute addressing, so a literal is correct there.
    assert build_mod.assemble_at("\tjsr 0x1234.l", 0x400) == bytes.fromhex("4eb900001234")


def test_ips_roundtrip():
    original = build_fixture_rom()
    modified = bytearray(original)
    modified[0x400:0x404] = b"\xde\xad\xbe\xef"
    modified[0x1234] = 0x99
    modified = bytes(modified)

    ips = patch_mod.create_ips(original, modified)
    assert ips.startswith(b"PATCH") and ips.endswith(b"EOF")
    assert patch_mod.apply_ips(original, ips) == modified


def test_ips_of_identical_roms_is_empty():
    rom = build_fixture_rom()
    ips = patch_mod.create_ips(rom, rom)
    assert ips == b"PATCH" + b"EOF"
    assert patch_mod.apply_ips(rom, ips) == rom


def test_ips_rejects_non_ips_input():
    with pytest.raises(patch_mod.PatchError, match="not an IPS patch"):
        patch_mod.apply_ips(b"\x00" * 16, b"nope")


def test_ips_rejects_shrinking_rom():
    with pytest.raises(patch_mod.PatchError, match="shorter"):
        patch_mod.create_ips(b"\x00" * 32, b"\x00" * 16)


def test_ips_splits_runs_longer_than_a_record():
    original = bytes(0x30000)
    modified = b"\xff" * 0x30000
    ips = patch_mod.create_ips(original, modified)
    assert patch_mod.apply_ips(original, ips) == modified


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_gas_condition_aliases_are_guarded():
    # hs/lo are GAS aliases for cc/cs; without them in the guard a
    # branch written that way assembles to a zero displacement.
    for src in ("\tbhs.w 0x420", "\tblo.w 0x420", "\tdbhs d0, 0x420"):
        with pytest.raises(build_mod.AssembleError, match="silently encode"):
            build_mod.assemble_at(src, 0x400)
    assert build_mod.assemble_at("\tbhs.w rom+0x420", 0x400) == bytes.fromhex("6400001e")
