# NHL '94 Remixed

A matching disassembly of NHL '94 (USA, Europe), plus mod tooling for
the cartridge.

**You supply your own cartridge.** Nothing derived from the ROM is in
this repository, and nothing derived from it can be committed — see
[ASSET_AUDIT.md](ASSET_AUDIT.md).

## What "matching disassembly" means, and why not C

NHL '94 was written in hand-written 68000 assembly, like nearly every
Genesis game. There is no C source to recover, so there is no honest C
decompilation to produce — anything claiming to be one is a rewrite.

The real target is a **matching disassembly**: annotated 68000 assembly,
split into named files, that reassembles to a byte-identical cartridge.
That is the standard the Sonic Retro and Kid Chameleon disassemblies set,
and it is what this project builds.

## The one invariant

The build reproduces the cartridge byte for byte, from the first commit.

With no regions declared, the whole ROM is a single `incbin` and the
rebuild matches trivially. Each identified routine replaces a slice of
that blob with committed assembly, and the rebuild either still matches
or the region is wrong. There is no in-between state to drift into.

So "how much is understood" only ever goes up, and a mistake is a failed
build rather than a subtly wrong ROM. This is deliberately the opposite
of disassembling outward from the entry points and measuring how far you
got.

## Setup

```sh
python3 tools/setup.py          # fetch + build the pinned assembler
cp "NHL '94 (USA, Europe).md" rom/nhl94.md
python3 tools/verify.py         # must print BIT-PERFECT
```

`tools/setup.py` needs Python 3.11+, `make`, and a C compiler. On
Windows use MSYS2/MinGW, or put a prebuilt `vasmm68k_mot` on your `PATH`
and skip setup — see [docs/SETUP.md](docs/SETUP.md).

The cartridge is identified by hash, not filename. An unrecognised dump
is rejected with its own digests printed so you can add it to
`tools/rom-lock.json` deliberately.

## Layout

| Path | What |
| --- | --- |
| `src/nhl94.asm` | Build root. Almost empty by design |
| `src/regions.json` | Identified code regions. Empty is the correct start |
| `src/code/` | Assembly for identified routines |
| `tools/split.py` | Carves the cartridge into blobs + identified code |
| `tools/build.py` | Assembles with `vasm -no-opt` |
| `tools/verify.py` | The bit-perfect gate |
| `tools/romcheck.py` | Identifies a dump by hash |
| `tools/candidates.py` | Ranks uncarved routines, cheapest first |
| `tools/lint.py` | Enforces the audit and the naming rule |
| `src/blocked.json` | Routines that resisted, and why |
| `docs/ROM_MAP.md` | Cartridge addresses, each with its evidence |
| `docs/RAM_MAP.md` | Where gameplay values live |
| `docs/FIDELITY.md` | What counts as evidence; deviations |
| `toolkit/` | Mod tooling: team names, patches, IPS, data maps |

## How to make progress

The highest-leverage step is **not** more static analysis. Capture a
code/data log from an emulator (BizHawk's CDL, Exodus, or Gens-KMod):
play every mode and the log records which bytes the CPU actually
executed, including which start an opcode. Following branches statically
reaches about 4.6% of this cartridge; a thorough log can reach most of
the real code.

Then work the queue. `tools/candidates.py` ranks the routines not yet
carved cheapest first, by instruction, branch and jump count:

```
  address   cost  bytes  insns  br  jmp  ends  note
 0x000418      3     10      3   0    0  yes
 0x000400     12     22      8   2    0  yes
```

Start at the top: disassemble it, name it, add it to `regions.json` with
its evidence, rebuild, confirm BIT-PERFECT, commit, run it again.
Ordering matters more than it looks — cheap routines land, and each one
adds an understood idiom that makes the expensive ones cheaper.

If a routine resists byte-exact reassembly, record *why* in
`src/blocked.json`. After ten recorded attempts it stops being offered,
so the queue cannot livelock on one stubborn case, and the reasons
accumulate into a punch list rather than a record of guesses.

## If you only want to mod the game

You do not need any of the above. Gameplay values live in RAM, and
`toolkit/` already edits team names and applies guarded patches:

```sh
genesis-toolkit map-list rom/nhl94.md toolkit/maps/nhl94-ue.json
genesis-toolkit map-set  rom/nhl94.md toolkit/maps/nhl94-ue.json mymod.json \
    --set team.BOS.city="Atomic" --set team.BOS.nickname="Rooms"
genesis-toolkit patch    rom/nhl94.md mymod.json out.md
```

28 teams, 112 named fields, header checksum fixed automatically, and
every edit carries an `expect` guard so it refuses to apply to the wrong
revision. See [GETTING-STARTED.md](GETTING-STARTED.md).

For speed and scoring, see the method in [docs/RAM_MAP.md](docs/RAM_MAP.md) —
an emulator RAM search plus a write breakpoint finds those in an
afternoon, with no disassembly required.

## State of the work

Read [VERIFICATION.md](VERIFICATION.md) before trusting anything here.
Short version: the pipeline is proven byte-exact on a synthetic fixture
and has not yet been run against the real cartridge, and
`src/regions.json` is empty.

## Credit

Structure modelled on [Resident Doom](https://github.com/Drelvak/Resident-Doom)
(pinned inputs, generate-locally, publication audit) and
[kid-chameleon-disasm](https://github.com/sonicretro/kid-chameleon-disasm)
(split-and-rebuild). Addresses cited in `docs/ROM_MAP.md` come partly
from KanedaFr's published IDA work. Full list in
[THIRD_PARTY.md](THIRD_PARTY.md).
