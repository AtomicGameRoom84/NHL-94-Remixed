"""Builds a tiny, entirely hand-authored Genesis-shaped ROM for tests.

Every byte here is either a standard-format header field we made up
ourselves (title strings, serial, region) or a handful of 68000
instructions we wrote from scratch to exercise a couple of addressing
modes and a branch. None of it is derived from, or resembles, any real
game's code or data -- it exists purely so the test suite has a fixture
it's allowed to ship.
"""
from __future__ import annotations

from pathlib import Path

from genesis_toolkit.header import compute_checksum


def _pad(s: str, n: int) -> bytes:
    return s.encode("ascii")[:n].ljust(n, b" ")


def build_fixture_rom() -> bytes:
    rom = bytearray(0x4000)

    code = bytes.fromhex(
        "203c00000100"    # move.l #0x100, d0        @0x400
        "4a40"            # tst.w d0                  @0x406
        "67f6"            # beq.b  0x400 (-10)         @0x408   (loops back to 'start')
        "6100000c"        # bsr.l  0x418               @0x40a  (call subroutine)
        "4e714e714e71"    # nop; nop; nop
        "4e75"            # rts (end of reset handler, never actually reached w/ bsr.l above -- fine for a fixture)
    )
    sub = bytes.fromhex(
        "48e7c0c0"        # movem.l d0-d1/a0-a1,-(sp)
        "4cdf0303"        # movem.l (sp)+,d0-d1/a0-a1
        "4e75"            # rts
    )

    reset_addr = 0x400
    sub_addr = 0x418
    assert 0x400 + len(code) <= sub_addr

    # --- vector table (bytes 0x000-0x0FF): 64 big-endian longwords ---
    rom[0:4] = (0x00FFFE00).to_bytes(4, "big")   # initial SP
    rom[4:8] = reset_addr.to_bytes(4, "big")     # reset PC
    for i in range(2, 64):
        rom[i * 4:i * 4 + 4] = (0).to_bytes(4, "big")
    # vblank interrupt (index 30) points at our subroutine too, purely
    # so code_entry_points() has a second entry point to discover.
    rom[30 * 4:30 * 4 + 4] = sub_addr.to_bytes(4, "big")

    # --- header (bytes 0x100-0x1FF) ---
    rom[0x100:0x110] = _pad("SEGA GENESIS", 16)
    rom[0x110:0x120] = _pad("(C)XX 2024.XXX", 16)
    rom[0x120:0x150] = _pad("GENESIS TOOLKIT TEST FIXTURE", 48)
    rom[0x150:0x180] = _pad("GENESIS TOOLKIT TEST FIXTURE", 48)
    rom[0x180:0x18E] = _pad("GT-00000000", 14)
    rom[0x190:0x1A0] = _pad("J", 16)
    rom[0x1A0:0x1A4] = (0x00000000).to_bytes(4, "big")
    rom[0x1A4:0x1A8] = (len(rom) - 1).to_bytes(4, "big")
    rom[0x1A8:0x1AC] = (0x00FF0000).to_bytes(4, "big")
    rom[0x1AC:0x1B0] = (0x00FFFFFF).to_bytes(4, "big")
    rom[0x1B0:0x1BC] = _pad("", 12)
    rom[0x1BC:0x1C8] = _pad("", 12)
    rom[0x1F0:0x1F3] = _pad("U", 3)

    # --- code ---
    rom[reset_addr:reset_addr + len(code)] = code
    rom[sub_addr:sub_addr + len(sub)] = sub

    # --- some inert data past the code, so the fixture also exercises
    # DataRun emission/round-trip, not just instructions ---
    tail_start = 0x500
    for i in range(tail_start, tail_start + 64):
        rom[i] = i & 0xFF

    checksum = compute_checksum(bytes(rom))
    rom[0x18E:0x190] = checksum.to_bytes(2, "big")

    return bytes(rom)


def main():
    out = Path(__file__).with_name("fixture.md")
    out.write_bytes(build_fixture_rom())
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
