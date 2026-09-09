"""68000 exception vector table, as laid out at the start of every
Genesis ROM (bytes 0x000-0x0FF): 64 big-endian longwords."""
from __future__ import annotations

from dataclasses import dataclass

VECTOR_NAMES = [
    "initial_sp",
    "reset_pc",
    "bus_error",
    "address_error",
    "illegal_instruction",
    "zero_divide",
    "chk_instruction",
    "trapv_instruction",
    "privilege_violation",
    "trace",
    "line_1010_emulator",
    "line_1111_emulator",
    "reserved_12",
    "reserved_13",
    "reserved_14",
    "uninitialized_interrupt",
    "reserved_16",
    "reserved_17",
    "reserved_18",
    "reserved_19",
    "reserved_20",
    "reserved_21",
    "reserved_22",
    "reserved_23",
    "spurious_interrupt",
    "irq_level_1",
    "irq_level_2_ext",
    "irq_level_3",
    "irq_level_4_hblank",
    "irq_level_5",
    "irq_level_6_vblank",
    "irq_level_7",
] + [f"trap_{i:02d}" for i in range(16)] + [f"reserved_{i}" for i in range(48, 64)]


@dataclass(frozen=True)
class VectorEntry:
    index: int
    name: str
    address: int


def parse_vector_table(rom: bytes) -> list[VectorEntry]:
    if len(rom) < 0x100:
        raise ValueError("file too small to contain a vector table")
    entries = []
    for i in range(64):
        off = i * 4
        value = int.from_bytes(rom[off:off + 4], "big")
        entries.append(VectorEntry(index=i, name=VECTOR_NAMES[i], address=value))
    return entries


def code_entry_points(rom: bytes) -> list[tuple[str, int]]:
    """Vector-table addresses that plausibly point at ROM code: the
    reset vector plus any exception/interrupt vector whose target falls
    inside the ROM image and is word-aligned. Used to seed recursive
    descent disassembly."""
    rom_len = len(rom)
    out = []
    for entry in parse_vector_table(rom):
        if entry.name == "initial_sp":
            continue
        addr = entry.address
        # Nothing below 0x200 can be real code: 0x000-0x0FF is the
        # vector table itself and 0x100-0x1FF is the cartridge header
        # (ASCII titles and range fields). An unset/reserved vector is
        # typically left as 0x000000, which would otherwise be misread
        # as "code starts at the beginning of the vector table".
        if addr % 2 == 0 and 0x200 <= addr < rom_len:
            out.append((entry.name, addr))
    return out
