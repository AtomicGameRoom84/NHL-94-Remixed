"""Regression tests for the recursive-descent walk's stopping conditions."""
from genesis_toolkit.disasm import recursive_descent


def test_dc_w_pseudo_instruction_stops_the_walk():
    # capstone doesn't reject every undecodable word -- for some it
    # emits a `dc.w $xxxx` data directive and keeps going. If the walk
    # accepted those it would march through data recording each word as
    # code, so they have to count as decode failures.
    rom = bytes.fromhex("ffffffffffffffff") * 4
    result = recursive_descent(rom, [("seed", 0)])
    assert result.instructions == {}
    assert result.decode_failures == [0]


def test_walk_stops_at_rts_without_falling_through():
    # nop; rts; then bytes that must not be decoded as a continuation.
    rom = bytes.fromhex("4e714e75") + bytes.fromhex("ffff") * 4
    result = recursive_descent(rom, [("seed", 0)])
    assert sorted(result.instructions) == [0x00, 0x02]
    assert result.instructions[0x02].mnemonic == "rts"
