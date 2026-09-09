from genesis_toolkit.header import parse_header
from tests.fixtures.make_fixture import build_fixture_rom


def test_header_fields_and_checksum():
    rom = build_fixture_rom()
    h = parse_header(rom)
    assert h.console_name == "SEGA GENESIS"
    assert h.domestic_title == "GENESIS TOOLKIT TEST FIXTURE"
    assert h.serial_number == "GT-00000000"
    assert h.checksum_ok
