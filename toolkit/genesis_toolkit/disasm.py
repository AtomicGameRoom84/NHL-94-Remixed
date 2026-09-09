"""Recursive-descent 68000 disassembler for Genesis ROMs.

Rather than blindly decoding every byte as an instruction (which
produces garbage the moment it walks into a data/graphics/audio blob),
this follows control flow from a set of known entry points -- the reset
vector, any exception/interrupt vectors that point into the ROM, plus
any extra addresses the caller supplies (e.g. discovered jump-table
targets). Anything never reached by that walk is emitted as data.

This is a heuristic, same as any disassembler applied to a binary with
no debug symbols: it will under-approximate code (some code reached only
through indirect jumps/jump tables won't be found) but it will not
mis-classify data as code the way a naive linear sweep does, which is
what matters for keeping the output re-assemblable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000

_HEXNUM = re.compile(r"\$([0-9A-Fa-f]+)")

_NO_FALLTHROUGH = {"rts", "rte", "rtr", "bra", "jmp"}
_CALL_LIKE = {"bsr", "jsr"}
_COND_BRANCH_PREFIXES = (
    "beq", "bne", "bcc", "bcs", "bge", "bgt", "ble", "blt",
    "bhi", "bls", "bpl", "bmi", "bvc", "bvs", "dbra", "dbcc", "dbcs",
    "dbeq", "dbne", "dbge", "dbgt", "dble", "dblt", "dbhi", "dbls",
    "dbpl", "dbmi", "dbvc", "dbvs", "dbf", "dbt",
)


@dataclass
class Instruction:
    address: int
    size: int
    mnemonic: str
    op_str: str
    raw: bytes


@dataclass
class DataRun:
    address: int
    size: int
    raw: bytes


@dataclass
class DisasmResult:
    rom_len: int
    instructions: dict[int, Instruction] = field(default_factory=dict)
    entry_points: list[tuple[str, int]] = field(default_factory=list)
    decode_failures: list[int] = field(default_factory=list)


def _branch_target(mnemonic: str, op_str: str) -> int | None:
    matches = _HEXNUM.findall(op_str)
    if not matches:
        return None
    return int(matches[-1], 16)


def _is_control_transfer(mnemonic: str) -> bool:
    base = mnemonic.split(".")[0]
    if base in _NO_FALLTHROUGH or base in _CALL_LIKE:
        return True
    return any(base.startswith(p) for p in _COND_BRANCH_PREFIXES)


def _falls_through(mnemonic: str) -> bool:
    base = mnemonic.split(".")[0]
    return base not in _NO_FALLTHROUGH


def recursive_descent(rom: bytes, entry_points: list[tuple[str, int]]) -> DisasmResult:
    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    md.detail = False

    result = DisasmResult(rom_len=len(rom), entry_points=list(entry_points))
    visited: set[int] = set()
    worklist: list[int] = [addr for _, addr in entry_points]

    while worklist:
        addr = worklist.pop()
        if addr in visited or addr < 0 or addr >= len(rom) or addr % 2:
            continue

        # Walk forward from this seed until a non-fallthrough
        # instruction, a decode failure, or territory we've already
        # covered.
        cur = addr
        while cur not in visited and 0 <= cur < len(rom) and cur % 2 == 0:
            window = bytes(rom[cur:cur + 24])
            insns = list(md.disasm(window, cur))
            # capstone stops at the first invalid opcode within the
            # window; if it decoded nothing, this address doesn't hold
            # a valid instruction.
            if not insns or insns[0].address != cur:
                result.decode_failures.append(cur)
                break

            insn = insns[0]
            if cur in result.instructions:
                break
            result.instructions[cur] = Instruction(
                address=cur, size=insn.size, mnemonic=insn.mnemonic,
                op_str=insn.op_str, raw=bytes(insn.bytes),
            )
            visited.add(cur)

            if _is_control_transfer(insn.mnemonic):
                target = _branch_target(insn.mnemonic, insn.op_str)
                if target is not None:
                    worklist.append(target)

            if not _falls_through(insn.mnemonic):
                break

            cur = cur + insn.size

    return result


def linear_map(result: DisasmResult, rom: bytes):
    """Produce the final ordered list of Instruction/DataRun spans
    covering the whole ROM contiguously, coalescing un-decoded bytes
    into DataRun blocks."""
    spans = []
    addr = 0
    data_start = None
    n = result.rom_len

    def close_data(end):
        nonlocal data_start
        if data_start is not None and end > data_start:
            spans.append(DataRun(address=data_start, size=end - data_start,
                                  raw=bytes(rom[data_start:end])))
        data_start = None

    while addr < n:
        insn = result.instructions.get(addr)
        if insn is not None:
            close_data(addr)
            spans.append(insn)
            addr += insn.size
        else:
            if data_start is None:
                data_start = addr
            addr += 1
    close_data(addr)
    return spans
