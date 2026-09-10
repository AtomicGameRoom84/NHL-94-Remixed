"""Dispatch-table discovery, exercised on a hand-authored fixture.

The two idioms tested here are the ones a real 68000 game actually
uses -- a base address in a register, jumped through indirectly -- but
every byte below was written for this test. The point of using a
fixture rather than a real ROM is that the expected answers are known
in advance: the tables, their lengths, and the routines they reach are
all placed deliberately, so a wrong result is a bug rather than a
judgement call about someone else's binary.
"""
from __future__ import annotations

import pytest

from genesis_toolkit import tables as T
from genesis_toolkit.disasm import recursive_descent

ROM_SIZE = 0x2000
LONG_TABLE = 0x600
WORD_TABLE = 0x700
LONG_TARGETS = [0x620, 0x628, 0x630, 0x638]
WORD_TARGETS = [0x708, 0x710, 0x718, 0x720]

# nop; rts -- short enough to place four of them, long enough that
# looks_like_code has to decode more than one instruction.
ROUTINE = bytes.fromhex("4e714e75")


def _put(rom: bytearray, at: int, data: bytes) -> None:
    rom[at:at + len(data)] = data


def build_dispatch_rom() -> bytes:
    rom = bytearray(ROM_SIZE)
    rom[0:4] = (0x00FFFE00).to_bytes(4, "big")
    rom[4:8] = (0x400).to_bytes(4, "big")          # reset vector

    # Reset calls each dispatcher so recursive descent reaches them.
    _put(rom, 0x400, bytes.fromhex("6100000e"))     # bsr.w 0x410
    _put(rom, 0x404, bytes.fromhex("6100002a"))     # bsr.w 0x430
    _put(rom, 0x408, bytes.fromhex("61000046"))     # bsr.w 0x450
    _put(rom, 0x40C, bytes.fromhex("4e75"))         # rts

    # Idiom A: absolute longword table, base arrives as an immediate.
    #   movea.l #$600,a0 / movea.l (a0,d1.w),a0 / jsr (a0)
    _put(rom, 0x410, bytes.fromhex("207c00000600"))
    _put(rom, 0x416, bytes.fromhex("20701000"))
    _put(rom, 0x41A, bytes.fromhex("4e90"))
    _put(rom, 0x41C, bytes.fromhex("4e75"))

    # Idiom B: word offsets from the base, which arrives via lea (pc).
    #   lea $700(pc),a2 / move.w (a2,d0.w),d0 / jsr (a2,d0.w)
    _put(rom, 0x430, bytes.fromhex("45fa02ce"))
    _put(rom, 0x434, bytes.fromhex("30320000"))
    _put(rom, 0x438, bytes.fromhex("4eb20000"))
    _put(rom, 0x43C, bytes.fromhex("4e75"))

    # Not resolvable by reading code: the pointer comes from RAM.
    #   movea.l $c000.w,a1 / jsr (a1)
    _put(rom, 0x450, bytes.fromhex("2278c000"))
    _put(rom, 0x454, bytes.fromhex("4e91"))
    _put(rom, 0x456, bytes.fromhex("4e75"))

    for i, target in enumerate(LONG_TARGETS):
        _put(rom, LONG_TABLE + 4 * i, target.to_bytes(4, "big"))
    # An odd, out-of-range longword: the table has to stop here.
    _put(rom, LONG_TABLE + 4 * len(LONG_TARGETS), b"\xff\xff\xff\xff")

    for i, target in enumerate(WORD_TARGETS):
        _put(rom, WORD_TABLE + 2 * i, (target - WORD_TABLE).to_bytes(2, "big"))

    for target in LONG_TARGETS + WORD_TARGETS:
        _put(rom, target, ROUTINE)
    return bytes(rom)


@pytest.fixture(scope="module")
def rom() -> bytes:
    return build_dispatch_rom()


@pytest.fixture(scope="module")
def found(rom):
    return T.discover(rom, [("reset", 0x400)], infer=False)


def test_finds_both_table_idioms(found):
    assert set(found.tables) == {LONG_TABLE, WORD_TABLE}


def test_longword_table_entries_are_read_as_addresses(found):
    assert found.tables[LONG_TABLE] == LONG_TARGETS


def test_word_table_entries_are_offsets_from_the_base(found):
    """The stored words are 0x08/0x10/0x18/0x20, not addresses. Reading
    them as absolute would point at the vector table instead."""
    assert found.tables[WORD_TABLE] == WORD_TARGETS


def test_word_table_stops_at_its_own_first_target(rom):
    """The routines sit immediately after the table, so entry five would
    be the first routine's opcodes read as an offset."""
    entries = T._word_rel_entries(rom, WORD_TABLE, T._md())
    assert len(entries) == len(WORD_TARGETS)
    assert min(entries) == WORD_TABLE + 2 * len(entries)


def test_longword_table_stops_at_a_non_address(rom):
    assert T._table_entries(rom, LONG_TABLE, T._md()) == LONG_TARGETS


def test_discovered_routines_become_entry_points(found):
    addrs = {addr for _, addr in found.entry_points}
    assert set(LONG_TARGETS + WORD_TARGETS) <= addrs


def test_entry_point_names_are_unique(found):
    """One table yields many routines. Naming them after the table
    instead of the target gives every one the same label, which the
    assembler rejects outright."""
    names = [name for name, _ in found.entry_points]
    assert len(names) == len(set(names))


def test_pointer_loaded_from_ram_is_not_guessed(rom):
    """`movea.l $c000.w,a1` puts a value known only at runtime into a1.
    Inventing a table base here is how a disassembler ends up decoding
    graphics data as code."""
    result = recursive_descent(rom, [("reset", 0x400)])
    ordered = sorted(result.instructions)
    i = ordered.index(0x454)                     # the jsr (a1)
    assert result.instructions[0x454].mnemonic.startswith("jsr")
    assert T._trace_table_base(result.instructions, ordered, i, "a1") is None


def test_discovery_reaches_code_that_seeds_alone_cannot(rom):
    seeds = [("reset", 0x400)]
    before = recursive_descent(rom, seeds)
    after = recursive_descent(rom, T.discover(rom, seeds, infer=False).entry_points)
    assert set(LONG_TARGETS + WORD_TARGETS) & set(before.instructions) == set()
    assert set(LONG_TARGETS + WORD_TARGETS) <= set(after.instructions)


def test_reader_that_writes_a_data_register_still_sets_the_width(rom):
    """`move.w (a2,d0.w),d0` names the table's register but writes d0.
    Screening on 'writes a2' before reading the width skips it, and the
    word table gets read as longwords."""
    result = recursive_descent(rom, [("reset", 0x400)])
    ordered = sorted(result.instructions)
    i = ordered.index(0x438)                     # the jsr (a2,d0.w)
    assert T._trace_table_base(result.instructions, ordered, i, "a2") == (
        WORD_TABLE, T.WORD_ENTRIES)


def test_register_clobbered_after_the_load_is_not_traced(rom):
    """If something else writes the register between the base load and
    the jump, the base no longer reaches the jump."""
    clobbered = bytearray(rom)
    # Overwrite `movea.l (a0,d1.w),a0` with `movea.l $c000.w,a0`,
    # so a0 no longer derives from the immediate at 0x410.
    _put(clobbered, 0x416, bytes.fromhex("2078c000"))
    result = recursive_descent(bytes(clobbered), [("reset", 0x400)])
    ordered = sorted(result.instructions)
    i = ordered.index(0x41A)
    assert T._trace_table_base(result.instructions, ordered, i, "a0") is None


def test_looks_like_code_rejects_the_header_and_odd_addresses(rom):
    md = T._md()
    assert not T.looks_like_code(rom, 0x100, md)   # cartridge header
    assert not T.looks_like_code(rom, 0x401, md)   # odd
    assert not T.looks_like_code(rom, ROM_SIZE, md)
    assert T.looks_like_code(rom, LONG_TARGETS[0], md)


def test_post_increment_counts_as_writing_the_register(rom):
    """`move.b (a0)+,d0` writes d0 and advances a0, but a0 appears only
    in the source operand. A trace that walks past it reports a base
    address that no longer reaches the jump."""
    moved = bytearray(rom)
    # Replace `movea.l (a0,d1.w),a0` (4 bytes) with
    # `move.b (a0)+,d0` + `nop`, so a0 is advanced, not re-derived.
    _put(moved, 0x416, bytes.fromhex("10184e71"))
    result = recursive_descent(bytes(moved), [("reset", 0x400)])
    ordered = sorted(result.instructions)
    i = ordered.index(0x41A)
    assert T._trace_table_base(result.instructions, ordered, i, "a0") is None
