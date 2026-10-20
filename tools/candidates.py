#!/usr/bin/env python3
"""Rank routines not yet carved, cheapest first.

The bottleneck in a matching disassembly is not capability, it is
ordering. Pick a hard routine first and you spend a day learning that
one encoding will not round-trip; pick the cheap ones first and each one
lands, the vocabulary of understood idioms grows, and the hard ones get
easier because their neighbours are already named.

So this answers "what next" with a cost estimate rather than a guess:
how many instructions, how many branches and jumps, and whether anything
in it is known to resist byte-exact reassembly.

Cost ordering is the part of the published agent decomp loop worth
taking (one N64 game: 2,145 functions in 84 days). The attempt cap from
that same loop is adapted rather than copied: in a C decomp an attempt
is a rewrite that the compiler either reproduces or does not, so ten
tries and move on makes sense. Here the disassembler hands over the
instruction stream and it either reassembles or it does not -- so what
is worth logging is the *reason* a routine resisted, in
`src/blocked.json`, which accumulates into a punch list instead of a
record of guesses.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "toolkit"))

from romcheck import DEFAULT_LOCK, RomError, identify  # noqa: E402

BLOCKED = ROOT / "src" / "blocked.json"
# Past this many recorded attempts a routine is held back rather than
# offered again, so the queue cannot livelock on one stubborn case.
ATTEMPT_CAP = 10


def _seeds(rom: bytes) -> list[tuple[str, int]]:
    from genesis_toolkit import vectors as vectors_mod
    seeds = [("reset", int.from_bytes(rom[4:8], "big"))]
    seeds += [(n, a) for n, a in vectors_mod.code_entry_points(rom)
              if n != "reset_pc"]
    return seeds


def _routine_extent(result, start: int, rom_len: int) -> tuple[int, dict]:
    """Walk one routine from `start`, returning its size and shape.

    Stops at the first instruction that does not fall through -- an
    rts/rte/bra/jmp -- which is where a 68000 routine ends. A routine
    whose end is never reached is reported with what was found, because
    an unterminated walk is itself a reason to rank it last.
    """
    from genesis_toolkit.disasm import _falls_through, _is_control_transfer

    # A return ends the routine; it has no target to reason about, so
    # counting it as a branch would make every routine look one step
    # more expensive than it is.
    returns = {"rts", "rte", "rtr"}
    at = start
    counts = {"instructions": 0, "branches": 0, "jumps": 0, "terminated": False}
    while at < rom_len:
        insn = result.instructions.get(at)
        if insn is None:
            break
        counts["instructions"] += 1
        base = insn.mnemonic.split(".")[0]
        if _is_control_transfer(insn.mnemonic) and base not in returns:
            # jmp/jsr name an absolute or indirect target; bcc/bsr/dbcc
            # are relative. Both add a target, the absolute ones more so
            # because an indirect target may not be knowable at all.
            if base in ("jmp", "jsr"):
                counts["jumps"] += 1
            else:
                counts["branches"] += 1
        at += insn.size
        if not _falls_through(insn.mnemonic):
            counts["terminated"] = True
            break
    return at - start, counts


def _covered(regions_path: Path) -> list[tuple[int, int]]:
    doc = json.loads(regions_path.read_text())
    return [(int(r["at"], 16), int(r["at"], 16) + r["size"])
            for r in doc.get("regions", [])]


def _blocked(path: Path = BLOCKED) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text()).get("routines", {})


def rank(rom_path: Path, regions_path: Path,
         lock_path: Path = DEFAULT_LOCK,
         blocked_path: Path = BLOCKED) -> list[dict]:
    from genesis_toolkit import tables as tables_mod
    from genesis_toolkit.disasm import recursive_descent

    identify(rom_path, lock_path)
    rom = rom_path.read_bytes()

    seeds = _seeds(rom)
    # Declared tables only. An inferred table's "routine" is a guess,
    # and offering guesses as work to do is how data gets carved as code.
    found = tables_mod.discover(rom, seeds, infer=False)
    result = recursive_descent(rom, found.entry_points)

    covered = _covered(regions_path)
    blocked = _blocked(blocked_path)
    out = []
    for name, start in found.entry_points:
        if any(lo <= start < hi for lo, hi in covered):
            continue
        if start not in result.instructions:
            continue
        size, shape = _routine_extent(result, start, len(rom))
        if size == 0:
            continue
        key = f"0x{start:06x}"
        record = blocked.get(key, {})
        attempts = record.get("attempts", 0)
        out.append({
            "at": key, "seed_name": name, "size": size,
            **shape,
            # Instructions dominate the work; a branch or a jump each add
            # a target to reason about, and an unterminated walk means
            # the extent itself is uncertain.
            "cost": shape["instructions"] + 2 * shape["branches"]
                    + 3 * shape["jumps"] + (0 if shape["terminated"] else 50),
            "attempts": attempts,
            "held": attempts >= ATTEMPT_CAP,
            "note": record.get("reason", ""),
        })
    out.sort(key=lambda r: (r["held"], r["cost"], r["size"]))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom", default=str(ROOT / "rom" / "nhl94.md"))
    p.add_argument("--regions", default=str(ROOT / "src" / "regions.json"))
    p.add_argument("--lock", default=str(DEFAULT_LOCK))
    p.add_argument("--blocked", default=str(BLOCKED))
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    try:
        ranked = rank(Path(a.rom), Path(a.regions), Path(a.lock),
                      Path(a.blocked))
    except RomError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(ranked, indent=2))
        return 0

    held = [r for r in ranked if r["held"]]
    live = [r for r in ranked if not r["held"]]
    print(f"{len(live)} routine(s) not yet carved"
          + (f", {len(held)} held at the attempt cap" if held else ""))
    if live:
        print(f"\n{'address':>9}  {'cost':>5} {'bytes':>6} {'insns':>6} "
              f"{'br':>3} {'jmp':>4}  ends  note")
        for r in live[:a.limit]:
            print(f"{r['at']:>9}  {r['cost']:>5} {r['size']:>6} "
                  f"{r['instructions']:>6} {r['branches']:>3} {r['jumps']:>4}"
                  f"  {'yes' if r['terminated'] else 'NO '}"
                  f"   {r['note']}")
        print("\nStart at the top. Carve it, confirm BIT-PERFECT, commit, "
              "then run this again.")
    for r in held:
        print(f"held  {r['at']}  after {r['attempts']} attempt(s): {r['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
