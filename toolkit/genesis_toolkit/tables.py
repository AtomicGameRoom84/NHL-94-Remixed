"""Finding the code recursive descent can't reach on its own.

Following control flow from the vector table finds only what a straight
line of branches and direct calls leads to. On a real game that is a
small fraction of the ROM, because the engine dispatches through
*tables*: a state number indexes an array of routine addresses and the
code jumps to whatever it finds there. Nothing in the instruction stream
names those routines, so a walk that only reads operands walks past
almost everything.

Two ways to find the tables:

**Declared** — the dispatching code names the table's base address in
an operand. NHL '94 never uses the textbook `jmp $1234(pc,d0.w)` form;
it loads the base into an address register first and jumps through that,
in one of two shapes:

    movea.l #$18d7c, a0        lea      $117b2(pc), a2
    movea.l (a0,d1.w), a0      move.w   (a2,d0.w), d0
    jsr     (a0)               jsr      (a2,d0.w)

Both name the base outright, so both are evidence. What differs is how
an entry is stored, and the *reader* instruction says which: a `.l` read
means the table holds absolute longword addresses, while a `.w` read
means it holds signed 16-bit offsets *from the table base*. Reading one
as the other yields nonsense, so the width is taken from the reader
rather than assumed.

**Inferred** — a run of consecutive longwords that all happen to be
even, inside the ROM, above the header, and land on bytes that decode
as code. Four such values in a row is already a strong signal: a random
longword has well under a 1-in-1000 chance of looking like a valid
Genesis code pointer, so a run of four is not something you stumble
into.

Both kinds are only accepted after the address they point at is decoded
and behaves like a function, so a table of coincidences doesn't quietly
turn half a graphics blob into "code". The search then repeats: routines
found through one table often contain the next one, so discovery runs to
a fixed point rather than a single pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs

from .disasm import _NO_FALLTHROUGH, recursive_descent

# `jmp`/`jsr` through a table indexed by a register: the operand carries
# the table's base address, e.g. "jmp $1234(pc,d0.w)".
_INDEXED_JUMP = re.compile(r"^(?:jmp|jsr)\b", re.IGNORECASE)
_TABLE_BASE = re.compile(
    r"\$([0-9A-Fa-f]+)\((?:pc|a[0-7])\s*,\s*d[0-7]", re.IGNORECASE)

# `jsr (a0)` / `jmp (a1)` / `jsr (a2,d0.w)` -- the destination is in an
# address register, so the base has to be recovered from earlier code.
_INDIRECT_DEST = re.compile(
    r"^\((a[0-7])(?:\s*,\s*d[0-7](?:\.[wl])?)?\)", re.IGNORECASE)

# The instruction that put a literal base address into that register.
# `lea $X(pc),aN` and `movea.l #$X,aN` are the two forms this game uses.
_LEA_PCREL = re.compile(
    r"^\$([0-9A-Fa-f]+)\(pc\)\s*,\s*(a[0-7])$", re.IGNORECASE)
_MOVEA_IMM = re.compile(
    r"^#\$([0-9A-Fa-f]+)\s*,\s*(a[0-7])$", re.IGNORECASE)

# Reading an entry out of the table: `(aN,dN.w)` as the *source*. Its
# size suffix is what tells us how wide an entry is.
_INDEXED_READ = re.compile(r"^\((a[0-7])\s*,\s*d[0-7]\.w\)\s*,", re.IGNORECASE)

LONG_ENTRIES = "long"       # absolute addresses
WORD_ENTRIES = "word-rel"   # signed 16-bit offsets from the table base

# Below this, a "pointer" is the vector table or the cartridge header.
_LOWEST_CODE = 0x200
# A random longword rarely satisfies every constraint; four in a row
# effectively never do by chance.
_MIN_TABLE_ENTRIES = 4


@dataclass
class Discovery:
    entry_points: list[tuple[str, int]] = field(default_factory=list)
    tables: dict[int, list[int]] = field(default_factory=dict)
    rounds: int = 0

    @property
    def discovered(self) -> int:
        return sum(len(v) for v in self.tables.values())


def _md():
    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    md.detail = False
    return md


def looks_like_code(rom: bytes, addr: int, md=None, depth: int = 12) -> bool:
    """Does `addr` behave like the start of a routine?

    Decoding a few instructions is not enough on its own -- plenty of
    data decodes into something. What separates a routine from a blob is
    that it *ends*: real code reaches an rts/rte/jmp, or keeps decoding
    cleanly for a while. Data tends to hit an invalid opcode, or capstone's
    `dc.w` filler, within a couple of words.
    """
    if addr % 2 or not (_LOWEST_CODE <= addr < len(rom)):
        return False
    md = md or _md()
    cur = addr
    for _ in range(depth):
        insns = list(md.disasm(bytes(rom[cur:cur + 24]), cur))
        if not insns or insns[0].address != cur:
            return False
        insn = insns[0]
        if insn.mnemonic.split(".")[0] == "dc":     # capstone's "undecodable"
            return False
        if "invalid" in insn.op_str:                # an operand it can't name
            return False
        if insn.mnemonic.split(".")[0] in _NO_FALLTHROUGH:
            return True                            # reached a clean end
        cur += insn.size
        if cur >= len(rom):
            return False
    return True                                    # still decoding cleanly


def _read_long(rom: bytes, at: int) -> int:
    return int.from_bytes(rom[at:at + 4], "big")


def _read_word_signed(rom: bytes, at: int) -> int:
    v = int.from_bytes(rom[at:at + 2], "big")
    return v - 0x10000 if v & 0x8000 else v


def _table_entries(rom: bytes, base: int, md) -> list[int]:
    """Read consecutive longword pointers from `base` while they keep
    looking like routine addresses."""
    out, at = [], base
    while at + 4 <= len(rom):
        target = _read_long(rom, at)
        if not looks_like_code(rom, target, md):
            break
        out.append(target)
        at += 4
    return out


def _word_rel_entries(rom: bytes, base: int, md) -> list[int]:
    """Read a table of signed 16-bit offsets measured from `base`.

    These tables have a terminator the longword kind doesn't: the
    routines they point at are laid out immediately after the table, so
    the lowest target is where the table stops. Reading past that point
    would start decoding the first routine's opcodes as more offsets, so
    the bound is tightened as each entry is read.
    """
    out, at, limit = [], base, len(rom)
    while at + 2 <= limit:
        target = base + _read_word_signed(rom, at)
        if not looks_like_code(rom, target, md):
            break
        out.append(target)
        at += 2
        limit = min(limit, min(out))
    return out


def _writes_register(insn, reg: str) -> bool:
    """Does this instruction leave a new value in `reg`?

    A destination operand is the obvious case, and only the destination
    counts: `move.w (a2,d0.w),d0` mentions a2 but writes d0, so it must
    not end a backward search for whatever set a2 -- otherwise the base
    load one instruction further back is never reached.

    Post-increment and pre-decrement are the non-obvious case. `move.b
    (a0)+,d0` writes d0 *and* advances a0, with a0 appearing only in the
    source. Missing that would let a trace walk back past an instruction
    that moved the register and report a base address that no longer
    reaches the jump.
    """
    if re.search(rf"\({reg}\)\+|-\({reg}\)", insn.op_str, re.IGNORECASE):
        return True
    ops = insn.op_str.rsplit(",", 1)
    return len(ops) == 2 and re.search(rf"\b{reg}\b", ops[1], re.IGNORECASE) is not None


def _trace_table_base(insns: dict, ordered: list[int], i: int, reg: str,
                      window: int = 24) -> tuple[int, str] | None:
    """Walk backwards from a register-indirect jump to the literal that
    set up its address register.

    Returns (base address, entry kind), or None when the base isn't a
    literal at all -- several dispatch sites load the pointer out of RAM
    (`movea.l $cf24.w,a0`), which no amount of static reading can
    resolve, and guessing there is how a disassembler wanders into a
    graphics blob.
    """
    kind = None
    for j in range(i - 1, max(-1, i - 1 - window), -1):
        prev = insns[ordered[j]]
        # Straight-line code only: a gap means the addresses aren't
        # contiguous, so this instruction may not actually precede the
        # jump at runtime.
        if prev.address + prev.size != insns[ordered[j + 1]].address:
            return None
        base_ops = prev.op_str
        # Check the indexed read before asking whether the register was
        # written. The read that reveals the entry width often writes a
        # *data* register (`move.w (a2,d0.w),d0`), so screening on
        # "writes a2" first would skip straight past it and lose the
        # width -- which is the whole reason for looking back.
        m = _INDEXED_READ.match(base_ops)
        if m and m.group(1).lower() == reg:
            kind = LONG_ENTRIES if prev.mnemonic.endswith(".l") else WORD_ENTRIES
            continue
        if not _writes_register(prev, reg):
            continue

        m = _LEA_PCREL.match(base_ops)
        if m and m.group(2).lower() == reg:
            # lea reaches the table as a PC-relative address; entries in
            # this form are always the word-offset kind in practice, but
            # only say so if a reader confirmed it.
            return int(m.group(1), 16), kind or WORD_ENTRIES
        m = _MOVEA_IMM.match(base_ops)
        if m and m.group(2).lower() == reg:
            return int(m.group(1), 16), kind or LONG_ENTRIES

        # Some other instruction clobbers the register; anything before
        # this point set a value that no longer reaches the jump.
        return None
    return None


def indirect_tables(result, rom: bytes, md=None) -> dict[int, list[int]]:
    """Tables reached through `jsr (aN)` / `jmp (aN,dN.w)`.

    The base address is still named by an instruction, just not by the
    jump itself, so these count as declared rather than guessed.
    """
    md = md or _md()
    ordered = sorted(result.instructions)
    found: dict[int, list[int]] = {}
    for i, addr in enumerate(ordered):
        insn = result.instructions[addr]
        if not _INDEXED_JUMP.match(insn.mnemonic):
            continue
        m = _INDIRECT_DEST.match(insn.op_str.strip())
        if not m:
            continue
        traced = _trace_table_base(result.instructions, ordered, i,
                                   m.group(1).lower())
        if traced is None:
            continue
        base, kind = traced
        if not (_LOWEST_CODE <= base < len(rom)):
            continue
        entries = (_table_entries(rom, base, md) if kind == LONG_ENTRIES
                   else _word_rel_entries(rom, base, md))
        if entries:
            found[base] = entries
    return found


def declared_tables(result, rom: bytes, md=None) -> dict[int, list[int]]:
    """Tables whose base address an instruction stated outright."""
    md = md or _md()
    found: dict[int, list[int]] = {}
    for insn in result.instructions.values():
        if not _INDEXED_JUMP.match(insn.mnemonic):
            continue
        m = _TABLE_BASE.search(insn.op_str)
        if not m:
            continue
        base = int(m.group(1), 16)
        if not (_LOWEST_CODE <= base < len(rom)):
            continue
        entries = _table_entries(rom, base, md)
        if entries:
            found[base] = entries
    found.update(indirect_tables(result, rom, md))
    return found


def inferred_tables(rom: bytes, known: set[int], md=None,
                    min_entries: int = _MIN_TABLE_ENTRIES) -> dict[int, list[int]]:
    """Runs of longwords that all look like routine addresses.

    Scans on 2-byte boundaries because 68000 tables are word-aligned but
    not necessarily longword-aligned.
    """
    md = md or _md()
    found: dict[int, list[int]] = {}
    at, end = _LOWEST_CODE, len(rom) - 4
    while at <= end:
        target = _read_long(rom, at)
        # Cheap rejection first; looks_like_code is the expensive part.
        if (target % 2 or not (_LOWEST_CODE <= target < len(rom))
                or at in known or not looks_like_code(rom, target, md)):
            at += 2
            continue
        entries = _table_entries(rom, at, md)
        if len(entries) >= min_entries:
            found[at] = entries
            at += 4 * len(entries)
        else:
            at += 2
    return found


def discover(rom: bytes, seeds: list[tuple[str, int]], *,
             infer: bool = True, max_rounds: int = 6) -> Discovery:
    """Walk, read the tables that walk exposed, walk again.

    Routines reached through one table routinely contain the next one, so
    a single pass under-reports; this repeats until a round finds nothing
    new.
    """
    md = _md()
    out = Discovery(entry_points=list(seeds))
    seen_targets = {addr for _, addr in seeds}

    for round_no in range(1, max_rounds + 1):
        out.rounds = round_no
        result = recursive_descent(rom, out.entry_points)

        tables = declared_tables(result, rom, md)
        if infer and round_no == 1:
            # The full scan is the expensive step and its results don't
            # change as more code is found, so do it once.
            tables.update(inferred_tables(rom, set(out.tables), md))

        fresh = []
        for base, entries in tables.items():
            out.tables.setdefault(base, entries)
            for target in entries:
                if target not in seen_targets:
                    seen_targets.add(target)
                    # Name after the routine, not the table it came from:
                    # one table yields many routines, and naming them all
                    # after the table gives every one of them the same
                    # label -- which the assembler rejects outright.
                    fresh.append((f"sub_{target:06x}", target))
        if not fresh:
            break
        out.entry_points.extend(fresh)
    return out
