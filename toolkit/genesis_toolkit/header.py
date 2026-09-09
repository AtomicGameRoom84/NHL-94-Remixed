"""Parser for the standard Sega Genesis / Mega Drive cartridge header.

Layout is fixed across every licensed Genesis game (it's checked by the
console's TMSS boot code), so this module is not specific to any single
ROM. Reference: the header occupies bytes 0x100-0x1FF; ROM/RAM range and
checksum fields sit just before it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenesisHeader:
    console_name: str
    copyright_release: str
    domestic_title: str
    overseas_title: str
    serial_number: str
    declared_checksum: int
    computed_checksum: int
    device_support: str
    rom_start: int
    rom_end: int
    ram_start: int
    ram_end: int
    extra_memory: str
    modem_support: str
    region_codes: str
    reserved: bytes

    @property
    def checksum_ok(self) -> bool:
        return self.declared_checksum == self.computed_checksum


def _ascii(raw: bytes) -> str:
    return raw.decode("ascii", errors="replace").rstrip()


def compute_checksum(rom: bytes) -> int:
    """Genesis checksum: 16-bit sum of every big-endian word from 0x200
    to the end of the cartridge, wrapping mod 0x10000.

    "End of the cartridge" is the ROM end address declared at 0x1A4, not
    necessarily the end of the file -- an overdumped or padded image has
    trailing bytes past it that the console (and the game's own
    self-check) never sums. Falls back to the file length when the
    declared end is missing or implausible.
    """
    total = 0
    declared_end = int.from_bytes(rom[0x1A4:0x1A8], "big") + 1 if len(rom) >= 0x1A8 else 0
    end = declared_end if 0x200 < declared_end <= len(rom) else len(rom)
    body = rom[0x200:end]
    if len(body) % 2:
        body = body + b"\x00"
    for i in range(0, len(body), 2):
        total = (total + ((body[i] << 8) | body[i + 1])) & 0xFFFF
    return total


def parse_header(rom: bytes) -> GenesisHeader:
    if len(rom) < 0x200:
        raise ValueError("file too small to contain a Genesis header")

    declared_checksum = (rom[0x18E] << 8) | rom[0x18F]

    return GenesisHeader(
        console_name=_ascii(rom[0x100:0x110]),
        copyright_release=_ascii(rom[0x110:0x120]),
        domestic_title=_ascii(rom[0x120:0x150]),
        overseas_title=_ascii(rom[0x150:0x180]),
        serial_number=_ascii(rom[0x180:0x18E]),
        declared_checksum=declared_checksum,
        computed_checksum=compute_checksum(rom),
        device_support=_ascii(rom[0x190:0x1A0]),
        rom_start=int.from_bytes(rom[0x1A0:0x1A4], "big"),
        rom_end=int.from_bytes(rom[0x1A4:0x1A8], "big"),
        ram_start=int.from_bytes(rom[0x1A8:0x1AC], "big"),
        ram_end=int.from_bytes(rom[0x1AC:0x1B0], "big"),
        extra_memory=_ascii(rom[0x1B0:0x1BC]),
        modem_support=_ascii(rom[0x1BC:0x1C8]),
        region_codes=_ascii(rom[0x1F0:0x1F3]),
        reserved=bytes(rom[0x1C8:0x1F0]),
    )
