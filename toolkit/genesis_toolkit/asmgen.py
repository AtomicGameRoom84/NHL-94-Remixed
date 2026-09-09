"""Emit GNU-as-compatible m68k assembly from a disasm span list.

Two translations are needed to go from capstone's M68K printer output to
something GNU as's m68k backend reproduces byte-for-byte:

1. Hex immediates: capstone prints Motorola-style ``$hex``; GAS wants
   ``0xhex``.
2. PC-relative targets: capstone resolves a Bcc/BSR/DBcc branch, or a
   ``lea``/``pea``/``move`` using ``(d16,PC)`` addressing, to an
   absolute address and prints that as a bare ``$hex`` literal
   (branches) or ``$hex(pc)`` (PC-relative addressing modes). Handing
   GAS that same literal back is a trap: for these specifically
   PC-relative-*encoded* operands, GAS treats a bare numeric operand as
   an already-computed displacement rather than resolving it against
   the current address the way it does for a symbol -- so it either
   truncates a branch displacement or silently embeds the wrong 16-bit
   ``(d16,PC)`` displacement. Both cases assemble without error and
   produce a subtly wrong ROM.

   The fix is what every assembler expects anyway: reference a label at
   the target address so GAS computes the displacement itself. Crucially
   this has to be a *real, positional* label (a name bound to an address
   by appearing at that point in the instruction stream) -- an absolute
   constant bound with ``.set`` looks identical when you read it back
   with ``nm``, but GAS's branch-relaxation logic doesn't treat it as a
   section-relative address and silently falls back to the same
   literal-displacement bug. So `emit_asm` splits any data span that a
   PC-relative operand points into, purely so a label can be placed
   exactly there.

   JMP/JSR are the odd ones out: capstone prints their absolute-mode
   targets the same bare-``$hex`` way it prints a branch's *relative*
   target, but the addressing mode is genuinely absolute (not
   PC-relative) -- GAS reassembles a literal absolute address for them
   correctly with no relocation involved, and forcing a label there
   backfires (see the ``.l``/``.w`` size-suffix note below). So this
   module only synthesizes labels for the mnemonics that truly encode a
   PC-relative field: Bcc/BSR/DBcc and any ``(pc)``-addressed operand,
   never bare-absolute JMP/JSR.

A couple of mnemonic/operand-level quirks in GNU as's m68k backend also
need massaging:

- It rejects a ``.l`` size suffix on ``exg`` (the instruction only has
  one size, so it doesn't accept one being spelled out).
- Its range check on ``moveq``'s signed 8-bit immediate wants a signed
  literal (``#-1``) rather than the unsigned ``#0xff`` capstone prints
  for the same bit pattern.
- A size suffix directly appended to a *symbol* (``label.l``, no space)
  only parses as "force this addressing mode" when the symbol is an
  absolute (``.set``) constant; on a real section-relative label it
  lexes as part of the identifier instead, silently referencing an
  undefined symbol. This module never appends a size suffix to a label
  reference for exactly that reason -- it only ever does so to a plain
  numeric literal, where it's unambiguous.

Data spans are emitted as raw .byte directives, which by construction
reassemble to identical bytes -- no translation risk there.
"""
from __future__ import annotations

import re

from .disasm import DataRun, Instruction, _branch_target, _is_control_transfer

_DOLLAR_HEX = re.compile(r"\$([0-9A-Fa-f]+)")
_MOVEQ_IMM = re.compile(r"#\$([0-9A-Fa-f]+)")
# A $hex immediately followed by "(pc" -- capstone's rendering of a
# resolved (d16,PC)/(d8,PC,Xn) effective address, e.g. "$28e(pc)".
_PCREL_HEX = re.compile(r"\$([0-9A-Fa-f]+)(?=\(pc\b)", re.IGNORECASE)


def _label_name(addr: int) -> str:
    return f"L{addr:06x}"


def _normalize_mnemonic(mnemonic: str) -> str:
    if mnemonic.split(".")[0] == "exg":
        return "exg"
    return mnemonic


def _fixup_moveq_immediate(mnemonic: str, op_str: str) -> str:
    if mnemonic != "moveq":
        return op_str

    def repl(m: re.Match) -> str:
        value = int(m.group(1), 16)
        if value > 0x7F:
            value -= 0x100
        return f"#{value}"

    return _MOVEQ_IMM.sub(repl, op_str, count=1)


_MOVE_L_IMM_TO_DN = re.compile(r"^#\$([0-9A-Fa-f]+), d[0-7]$")


def _gas_would_relax_to_moveq(mnemonic: str, op_str: str) -> bool:
    """GNU as's m68k backend silently re-encodes ``move.l #imm,Dn`` as
    the 2-byte MOVEQ form whenever the immediate's value is
    representable as a sign-extended byte -- unconditionally, with no
    flag to disable it. (move.w/move.b are not affected: unlike
    move.l, they don't touch the whole register, so they aren't
    equivalent to moveq and GAS leaves them alone.) That's a real,
    deterministic difference from whatever assembler produced the
    original ROM whenever *it* chose the longer MOVE encoding for a
    value moveq could hold. Since it's fully predictable from the
    operand text alone, instructions matching it are routed straight
    to a raw byte dump in emit_asm rather than spent on a GAS
    assemble-and-diff cycle to discover the same thing."""
    if mnemonic != "move.l":
        return False
    m = _MOVE_L_IMM_TO_DN.match(op_str)
    if not m:
        return False
    value = int(m.group(1), 16) & 0xFFFFFFFF
    return value <= 0x7F or value >= 0xFFFFFF80


def _is_relative_branch(mnemonic: str) -> bool:
    """True relative-displacement branches: Bcc/BSR/DBcc. Excludes
    JMP/JSR, whose bare-$hex operand form is absolute addressing, not a
    PC-relative field -- see module docstring."""
    base = mnemonic.split(".")[0]
    if base in ("jmp", "jsr"):
        return False
    return _is_control_transfer(mnemonic)


def _collect_positional_targets(spans, rom_len: int) -> set[int]:
    """Addresses that need a *real* label placed at that exact byte
    offset: relative-branch targets and any (pc)-relative operand."""
    targets: set[int] = set()
    for span in spans:
        if not isinstance(span, Instruction):
            continue
        if _is_relative_branch(span.mnemonic):
            t = _branch_target(span.mnemonic, span.op_str)
            if t is not None and 0 <= t < rom_len:
                targets.add(t)
        for m in _PCREL_HEX.finditer(span.op_str):
            t = int(m.group(1), 16)
            if 0 <= t < rom_len:
                targets.add(t)
    return targets


def _split_spans_at(spans, addrs: set[int]):
    """Split any DataRun that contains one of `addrs` strictly inside
    it, so every such address becomes a span start a label can be
    attached to. Instructions are never split -- a target address
    landing mid-instruction means recursive descent's decode disagreed
    with this reference, which asmgen can't resolve; it's left as an
    unresolved literal downstream and surfaces via the verify/patch
    loop instead."""
    out = []
    for span in spans:
        if not isinstance(span, DataRun):
            out.append(span)
            continue
        start, end = span.address, span.address + span.size
        cuts = sorted(a for a in addrs if start < a < end)
        if not cuts:
            out.append(span)
            continue
        prev = start
        for cut in cuts:
            out.append(DataRun(address=prev, size=cut - prev,
                                raw=span.raw[prev - start:cut - start]))
            prev = cut
        out.append(DataRun(address=prev, size=end - prev,
                            raw=span.raw[prev - start:end - start]))
    return out


def _rewrite_operands(insn: Instruction, labels: dict[int, str]) -> str:
    op_str = _fixup_moveq_immediate(insn.mnemonic, insn.op_str)

    if _PCREL_HEX.search(op_str):
        def pcrel_repl(m: re.Match) -> str:
            target = int(m.group(1), 16)
            return labels.get(target, f"0x{m.group(1)}")
        op_str = _PCREL_HEX.sub(pcrel_repl, op_str)
    elif _is_relative_branch(insn.mnemonic):
        target = _branch_target(insn.mnemonic, insn.op_str)
        if target is not None and target in labels:
            # Replace only the final $hex token (the resolved target);
            # any earlier operand (e.g. the counter register in a DBcc)
            # is left untouched by only substituting the last match.
            matches = list(_DOLLAR_HEX.finditer(op_str))
            last = matches[-1]
            return op_str[:last.start()] + labels[target] + op_str[last.end():]

    return _DOLLAR_HEX.sub(lambda m: f"0x{m.group(1)}", op_str)


def emit_asm(spans, entry_points: list[tuple[str, int]], rom_len: int) -> str:
    positional_targets = _collect_positional_targets(spans, rom_len)
    positional_targets.update(addr for _, addr in entry_points if 0 <= addr < rom_len)
    spans = _split_spans_at(spans, positional_targets)

    labels: dict[int, str] = {addr: name for name, addr in entry_points}
    for addr in positional_targets:
        labels.setdefault(addr, _label_name(addr))

    lines = ["\t.org 0"]
    for span in spans:
        if span.address in labels:
            lines.append(f"{labels[span.address]}:")
        if isinstance(span, Instruction):
            if _gas_would_relax_to_moveq(span.mnemonic, span.op_str):
                byte_list = ",".join(f"0x{b:02x}" for b in span.raw)
                lines.append(f"\t.byte {byte_list}"
                              f"\t/* {span.address:06x}: {span.raw.hex()}"
                              f" (move.l->moveq relax avoided) */")
                continue
            op = _rewrite_operands(span, labels)
            mnemonic = _normalize_mnemonic(span.mnemonic)
            text = f"\t{mnemonic}\t{op}".rstrip()
            lines.append(f"{text}\t/* {span.address:06x}: {span.raw.hex()} */")
        elif isinstance(span, DataRun):
            lines.append(f"\t/* data: {span.address:06x}-{span.address + span.size:06x} */")
            for off in range(0, len(span.raw), 16):
                chunk = span.raw[off:off + 16]
                lines.append("\t.byte " + ",".join(f"0x{b:02x}" for b in chunk))
        else:  # pragma: no cover - defensive
            raise TypeError(f"unknown span type {type(span)!r}")
    return "\n".join(lines) + "\n"
