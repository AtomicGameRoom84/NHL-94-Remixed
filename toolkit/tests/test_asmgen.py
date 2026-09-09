"""Regression tests for the capstone->GAS translation quirks documented
in asmgen.py's module docstring -- each one was found by round-tripping
a real ROM through the toolkit and caused either a build error or (more
dangerously) a *silent* wrong-byte reassembly."""
from genesis_toolkit import asmgen


def test_moveq_immediate_signed():
    assert asmgen._fixup_moveq_immediate("moveq", "#$ff, d1") == "#-1, d1"
    assert asmgen._fixup_moveq_immediate("moveq", "#$7f, d2") == "#127, d2"
    assert asmgen._fixup_moveq_immediate("move.l", "#$ff, d1") == "#$ff, d1"


def test_exg_size_suffix_stripped():
    assert asmgen._normalize_mnemonic("exg.l") == "exg"
    assert asmgen._normalize_mnemonic("move.l") == "move.l"


def test_move_l_immediate_to_dn_relax_detection():
    # GAS silently re-encodes these as the 2-byte MOVEQ form.
    assert asmgen._gas_would_relax_to_moveq("move.l", "#$1b, d0")
    # $ffffffff is the 32-bit value -1, which fits a signed byte too.
    assert asmgen._gas_would_relax_to_moveq("move.l", "#$ffffffff, d3")
    # Out of moveq's signed-byte range: GAS keeps the full move.l. $ff
    # as a literal move.l immediate means +255, not sign-extended -1.
    assert not asmgen._gas_would_relax_to_moveq("move.l", "#$ff, d1")
    assert not asmgen._gas_would_relax_to_moveq("move.l", "#$100, d1")
    # move.w/move.b are not equivalent to moveq (they don't touch the
    # whole register) and GAS does not relax them.
    assert not asmgen._gas_would_relax_to_moveq("move.w", "#$1b, d0")
    assert not asmgen._gas_would_relax_to_moveq("move.b", "#$1b, d0")
    # Only a bare data-register destination triggers it.
    assert not asmgen._gas_would_relax_to_moveq("move.l", "#$1b, (a0)")


def test_relative_branch_excludes_jmp_jsr():
    assert asmgen._is_relative_branch("beq.b")
    assert asmgen._is_relative_branch("bsr.w")
    assert asmgen._is_relative_branch("dbra")
    assert not asmgen._is_relative_branch("jmp")
    assert not asmgen._is_relative_branch("jsr")


def test_unbindable_branch_target_falls_back_to_raw_bytes():
    # The target (0x06) lands inside the 6-byte instruction at 0x04, so
    # no label can be placed there. Emitting a reference to an undefined
    # label would assemble silently to zeros, so the branch must come
    # out as its original bytes instead.
    from genesis_toolkit.disasm import Instruction

    spans = [
        Instruction(address=0x00, size=4, mnemonic="bsr.w", op_str="$6",
                    raw=bytes.fromhex("61000002")),
        Instruction(address=0x04, size=6, mnemonic="move.l", op_str="#$100, d0",
                    raw=bytes.fromhex("203c00000100")),
    ]
    text = asmgen.emit_asm(spans, [("reset", 0)], rom_len=0x10)
    assert "L000006" not in text
    assert "0x61,0x00,0x00,0x02" in text


def test_pcrel_and_branch_labels_are_positional_not_set():
    # emit_asm must place a real "name:" label at every branch/PC-
    # relative target -- an absolute .set constant looks identical to
    # `nm` but GAS's branch-displacement relaxation doesn't treat it as
    # a real address (see the moveq/exg-style bug class this guards).
    from genesis_toolkit.disasm import Instruction

    spans = [
        Instruction(address=0, size=2, mnemonic="beq.b", op_str="$0", raw=b"\x67\xfe"),
    ]
    text = asmgen.emit_asm(spans, [("reset", 0)], rom_len=2)
    assert ".set" not in text
    assert "reset:" in text or "L000000:" in text
