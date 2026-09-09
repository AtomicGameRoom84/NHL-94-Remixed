from genesis_toolkit.vectors import code_entry_points, parse_vector_table
from tests.fixtures.make_fixture import build_fixture_rom


def test_vector_table_reset_and_vblank():
    rom = build_fixture_rom()
    vectors = parse_vector_table(rom)
    assert vectors[1].name == "reset_pc"
    assert vectors[1].address == 0x400
    assert vectors[30].name == "irq_level_6_vblank"
    assert vectors[30].address == 0x418


def test_code_entry_points_excludes_zeroed_reserved_vectors():
    rom = build_fixture_rom()
    entries = dict(code_entry_points(rom))
    assert entries["reset_pc"] == 0x400
    assert entries["irq_level_6_vblank"] == 0x418
    # every other vector in the fixture is 0x00000000, inside the
    # vector table itself, and must not show up as a bogus entry point.
    assert len(entries) == 2
