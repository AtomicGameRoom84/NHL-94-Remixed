"""The selftest is a green light, so it has to be able to go red."""
import json
from pathlib import Path

from genesis_toolkit import selftest
from tests.fixtures.make_fixture import build_fixture_rom


def _write_rom(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "rom.md"
    path.write_bytes(data)
    return path


def _status(result, name_fragment: str) -> str:
    for status, name, _ in result.checks:
        if name_fragment in name:
            return status
    raise AssertionError(f"no check matching {name_fragment!r} in "
                         f"{[n for _, n, _ in result.checks]}")


def test_clean_rom_passes_everything(tmp_path: Path):
    result = selftest.run(_write_rom(tmp_path, build_fixture_rom()),
                          workdir=tmp_path)
    assert result.failed == 0, result.checks
    assert _status(result, "checksum self-consistent") == selftest.PASS
    assert _status(result, "expect guard") == selftest.PASS
    assert _status(result, "untouched") == selftest.PASS


def test_bad_checksum_is_caught(tmp_path: Path):
    rom = bytearray(build_fixture_rom())
    rom[0x18E] ^= 0xFF
    result = selftest.run(_write_rom(tmp_path, bytes(rom)), workdir=tmp_path)
    assert _status(result, "checksum mismatch") == selftest.FAIL
    assert result.failed >= 1


def test_map_for_a_different_rom_is_caught(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({
        "rom_sha256": "00" * 32,
        "fields": [{"name": "title", "at": "0x120", "type": "str", "size": 48}],
    }))
    result = selftest.run(_write_rom(tmp_path, build_fixture_rom()),
                          map_path=map_path, workdir=tmp_path)
    assert _status(result, "data map") == selftest.FAIL


def test_map_pointing_off_the_end_is_caught(tmp_path: Path):
    rom = build_fixture_rom()
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({
        "fields": [{"name": "nope", "at": hex(len(rom) + 0x100), "type": "u32"}],
    }))
    result = selftest.run(_write_rom(tmp_path, rom), map_path=map_path,
                          workdir=tmp_path)
    assert _status(result, "every mapped field reads") == selftest.FAIL


def test_assembly_failure_is_blamed_on_reassembly_not_disassembly(tmp_path: Path):
    # A failure here must not surface as a second "disassembles" row
    # contradicting the PASS one, nor silently drop the reassembly row.
    from unittest.mock import patch as mock_patch

    from genesis_toolkit import build as build_mod

    rom = _write_rom(tmp_path, build_fixture_rom())
    with mock_patch.object(build_mod, "assemble_and_reconcile",
                           side_effect=build_mod.AssembleError("boom")):
        result = selftest.run(rom, workdir=tmp_path)

    names = [name for _, name, _ in result.checks]
    assert names.count("disassembles") == 1
    assert _status(result, "disassembles") == selftest.PASS
    assert _status(result, "reassembles byte-exact") == selftest.FAIL


def test_scratch_files_are_cleaned_up(tmp_path: Path):
    selftest.run(_write_rom(tmp_path, build_fixture_rom()), workdir=tmp_path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith("selftest")]
    assert leftovers == []
