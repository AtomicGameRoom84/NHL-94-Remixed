"""Reassemble a genesis_toolkit .s file back into a raw binary using GNU
binutils' m68k target, and compare it against a reference ROM.

This is the toolkit's correctness check: if `verify()` reports a full
match, the disassembly + asmgen output for that ROM is a byte-exact,
round-trippable representation. Where it doesn't match, the mismatch
report tells you exactly which addresses diverged, which is the
starting point for the (inherently manual) work of fixing up the
disassembly -- annotating a mis-classified data region, adding a missed
jump-table entry point, etc.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

AS = "m68k-linux-gnu-as"
OBJCOPY = "m68k-linux-gnu-objcopy"


class AssembleError(RuntimeError):
    pass


def assemble(asm_path: Path, out_bin: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        obj_path = Path(tmp) / "out.o"
        proc = subprocess.run(
            [AS, "-march=68000", "--register-prefix-optional",
             "-o", str(obj_path), str(asm_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise AssembleError(proc.stdout + proc.stderr)

        proc = subprocess.run(
            [OBJCOPY, "-O", "binary", str(obj_path), str(out_bin)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise AssembleError(proc.stdout + proc.stderr)


_ERROR_LINE = re.compile(r":(\d+): Error:")
_INSN_COMMENT = re.compile(r"/\* ([0-9a-fA-F]{6}): ([0-9a-fA-F]+) \*/")


def _error_line_numbers(as_output: str) -> set[int]:
    return {int(m.group(1)) for m in _ERROR_LINE.finditer(as_output)}


def patch_unassemblable(asm_text: str, as_output: str) -> tuple[str, list[tuple[int, int]]]:
    """Replace every line GAS rejected with a raw .byte dump of the
    original instruction bytes, recovered from the trailing
    ``/* address: hexbytes */`` comment genesis_toolkit.asmgen embeds on
    every instruction line. Returns the patched source and a list of
    (line_number, address) that got patched -- exactly the instruction
    forms this toolkit's capstone-to-GAS translator doesn't yet handle,
    which is the punch list for improving it.
    """
    lines = asm_text.splitlines()
    patched: list[tuple[int, int]] = []
    for lineno in sorted(_error_line_numbers(as_output)):
        idx = lineno - 1
        if not (0 <= idx < len(lines)):
            continue
        m = _INSN_COMMENT.search(lines[idx])
        if not m:
            continue
        addr_hex, raw_hex = m.group(1), m.group(2)
        raw = bytes.fromhex(raw_hex)
        byte_list = ",".join(f"0x{b:02x}" for b in raw)
        lines[idx] = (f"\t.byte {byte_list}"
                       f"\t/* UNPATCHED (asm rejected) {addr_hex}: {raw_hex} */")
        patched.append((lineno, int(addr_hex, 16)))
    return "\n".join(lines) + "\n", patched


def _assemble_patching_rejects(text: str, out_bin: Path,
                                max_passes: int) -> tuple[str, list[tuple[int, int]]]:
    """Assemble `text`; if GAS rejects some lines, patch just those with
    raw byte dumps of the original instruction and retry. Returns the
    (possibly patched) source that assembled cleanly, plus the
    (line_number, address) pairs that had to be patched."""
    all_patched: list[tuple[int, int]] = []
    with tempfile.TemporaryDirectory() as tmp:
        cur_path = Path(tmp) / "current.s"
        cur_path.write_text(text)
        last_error: AssembleError | None = None
        for _ in range(max_passes):
            try:
                assemble(cur_path, out_bin)
                return cur_path.read_text(), all_patched
            except AssembleError as e:
                last_error = e
                patched_text, patched = patch_unassemblable(cur_path.read_text(), str(e))
                if not patched:
                    raise
                all_patched.extend(patched)
                cur_path.write_text(patched_text)
        raise last_error


def assemble_best_effort(asm_path: Path, out_bin: Path,
                          max_passes: int = 5) -> list[tuple[int, int]]:
    """Assemble asm_path; if GAS rejects some instructions, patch just
    those lines with raw byte dumps of the original bytes and retry,
    writing the reconciled source back to asm_path so the rest of the
    file can still be verified/chained further. Returns the list of
    (line_number, address) that had to be patched -- empty if the file
    assembled cleanly on the first pass."""
    text, patched = _assemble_patching_rejects(asm_path.read_text(), out_bin, max_passes)
    if patched:
        asm_path.write_text(text)
    return patched


_INSN_LINE = re.compile(r"^\t\S.*\t/\* ([0-9a-fA-F]{6}): ([0-9a-fA-F]+) \*/$")


def patch_byte_mismatches(asm_text: str, reference: bytes,
                           rebuilt: bytes) -> tuple[str, list[tuple[int, int]]]:
    """Some instruction forms disassemble to text that GAS accepts but
    re-encodes differently than the original ROM's assembler did (e.g.
    68000 has two distinct opcodes for "compare immediate to a data
    register" -- CMPI and CMP-with-an-immediate-source -- that print
    identically as ``cmp.b #imm,dn``; GAS's mnemonic table always picks
    one of them). GAS reports no error for these -- the file just
    doesn't come back byte-identical. This scans every instruction span
    (using the same ``/* address: hexbytes */`` comment as
    patch_unassemblable) and replaces any whose rebuilt bytes don't
    match the reference with a raw .byte dump of the original bytes.
    """
    lines = asm_text.splitlines()
    patched: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        m = _INSN_LINE.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        raw = bytes.fromhex(m.group(2))
        size = len(raw)
        if addr + size > len(rebuilt) or addr + size > len(reference):
            continue
        if rebuilt[addr:addr + size] != reference[addr:addr + size]:
            byte_list = ",".join(f"0x{b:02x}" for b in raw)
            lines[i] = (f"\t.byte {byte_list}"
                         f"\t/* UNPATCHED (re-encoded differently) {m.group(1)}: {m.group(2)} */")
            patched.append((i + 1, addr))
    return "\n".join(lines) + "\n", patched


def assemble_and_reconcile(reference: bytes, asm_path: Path, out_bin: Path,
                            max_passes: int = 10) -> list[tuple[str, int, int]]:
    """The full round-trip loop: assemble (patching anything GAS
    outright rejects), then patch any instruction whose reassembled
    bytes don't match the reference ROM even though GAS accepted it,
    repeating until the rebuilt binary matches or no further progress
    is possible. Writes the fully reconciled source back to asm_path.
    Returns (reason, line_number, address) for everything patched --
    reason is "gas-reject" or "byte-mismatch".
    """
    text = asm_path.read_text()
    all_patched: list[tuple[str, int, int]] = []
    for _ in range(max_passes):
        text, gas_patched = _assemble_patching_rejects(text, out_bin, max_passes)
        all_patched.extend(("gas-reject", ln, addr) for ln, addr in gas_patched)

        rebuilt = out_bin.read_bytes()
        if rebuilt == reference:
            break
        text, mismatches = patch_byte_mismatches(text, reference, rebuilt)
        if not mismatches:
            break
        all_patched.extend(("byte-mismatch", ln, addr) for ln, addr in mismatches)
    asm_path.write_text(text)
    return all_patched


@dataclass
class VerifyReport:
    reference_len: int
    rebuilt_len: int
    first_mismatch: int | None
    mismatched_bytes: int
    matched_bytes: int

    @property
    def exact_match(self) -> bool:
        return (self.reference_len == self.rebuilt_len
                and self.first_mismatch is None)

    def summary(self) -> str:
        if self.exact_match:
            return f"EXACT MATCH ({self.reference_len} bytes)"
        pct = 100.0 * self.matched_bytes / max(self.reference_len, 1)
        diff = (f"first_diff=0x{self.first_mismatch:06x} "
                if self.first_mismatch is not None else "")
        return (f"MISMATCH: reference={self.reference_len}B rebuilt={self.rebuilt_len}B "
                f"{diff}matched={self.matched_bytes}B ({pct:.2f}%)")


def verify(reference: bytes, rebuilt: bytes) -> VerifyReport:
    matched = 0
    first_mismatch = None
    for i in range(min(len(reference), len(rebuilt))):
        if reference[i] == rebuilt[i]:
            matched += 1
        elif first_mismatch is None:
            first_mismatch = i
    return VerifyReport(
        reference_len=len(reference),
        rebuilt_len=len(rebuilt),
        first_mismatch=first_mismatch,
        mismatched_bytes=min(len(reference), len(rebuilt)) - matched,
        matched_bytes=matched,
    )
