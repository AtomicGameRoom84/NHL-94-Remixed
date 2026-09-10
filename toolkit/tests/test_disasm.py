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


def test_register_relative_target_is_not_an_address():
    # `jsr $6(a0)` jumps 6 bytes past whatever a0 holds at runtime.
    # Reading the 6 as an address enqueues the vector table as code.
    from genesis_toolkit.disasm import _branch_target
    assert _branch_target("jsr", "$6(a0)") is None
    assert _branch_target("jsr", "$10(a0,d0.w)") is None
    # PC-relative and absolute forms are still real addresses.
    assert _branch_target("jsr", "$1234.l") == 0x1234
    assert _branch_target("bra.w", "$420") == 0x420


def test_walk_does_not_wander_into_the_vector_table():
    # A register-indirect call must not seed address 0 as code.
    from genesis_toolkit.disasm import recursive_descent
    rom = bytes.fromhex("4eb00006") + bytes.fromhex("4e75") + bytes(64)
    result = recursive_descent(rom, [("seed", 0)])
    assert 0x6 not in result.instructions
