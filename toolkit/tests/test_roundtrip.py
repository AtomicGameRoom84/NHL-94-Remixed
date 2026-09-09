from pathlib import Path

import pytest

from genesis_toolkit import build as build_mod
from genesis_toolkit.asmgen import emit_asm
from genesis_toolkit.disasm import linear_map, recursive_descent
from genesis_toolkit.vectors import code_entry_points
from tests.fixtures.make_fixture import build_fixture_rom


def _has_m68k_as() -> bool:
    import shutil
    return shutil.which(build_mod.AS) is not None


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_disasm_reassemble_roundtrip(tmp_path: Path):
    rom = build_fixture_rom()
    entry_points = [("reset", int.from_bytes(rom[4:8], "big"))]
    entry_points += [
        (name, addr) for name, addr in code_entry_points(rom) if name != "reset_pc"
    ]

    result = recursive_descent(rom, entry_points)
    spans = linear_map(result, rom)
    asm_text = emit_asm(spans, entry_points, len(rom))

    asm_path = tmp_path / "fixture.s"
    asm_path.write_text(asm_text)
    out_bin = tmp_path / "fixture.bin"
    build_mod.assemble(asm_path, out_bin)

    report = build_mod.verify(rom, out_bin.read_bytes())
    assert report.exact_match, report.summary()


def test_recursive_descent_finds_both_entry_points():
    rom = build_fixture_rom()
    entry_points = [("reset", 0x400), ("vblank", 0x418)]
    result = recursive_descent(rom, entry_points)
    assert 0x400 in result.instructions
    assert 0x418 in result.instructions
    assert not result.decode_failures
