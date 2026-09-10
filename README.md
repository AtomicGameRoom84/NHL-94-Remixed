# NHL-94-Remixed

A modding toolkit for Sega Genesis / Mega Drive ROMs, built while taking
apart NHL '94 but deliberately not tied to it.

Everything here works from a ROM *you* supply. No ROM, no disassembly of
one, and no game content lives in this repository — see
[What's deliberately not here](#whats-deliberately-not-here).

**New to this? Start with [GETTING-STARTED.md](GETTING-STARTED.md)** --
a step-by-step Windows walkthrough from installing Python to seeing your
first mod in an emulator, with a way to check each step worked.

## The mental model

The thing people usually trip over: **you don't patch the disassembly,
you patch the ROM.** The disassembly is a *view* of the ROM you consult
to work out what to change.

```
  your ROM  ──disasm──▶  game.s        a reference view, ~6 MB of 68000 asm
     │                                 regenerated on demand, never stored
     │
     └──────patch───▶  modded.md       what you actually play
                ▲
             mod.json                  your edits: small, diffable, in git
```

Because `game.s` is reproducible from your own ROM in one command, it
never needs to be committed — which is also why you won't find it here.

## Quick start

```
cd toolkit
pip install -e .

genesis-toolkit header   "your rom.md"                       # what am I holding?
genesis-toolkit map-list "your rom.md" maps/nhl94-ue.json    # named fields
genesis-toolkit map-set  "your rom.md" maps/nhl94-ue.json mymod.json \
                         --set "team.TOR.nickname=Blue Jays"
genesis-toolkit patch    "your rom.md" mymod.json modded.md  # runnable ROM
genesis-toolkit ips-create "your rom.md" modded.md mymod.ips # shareable patch
```

Load `modded.md` in any emulator (BlastEm, Genesis Plus GX, Exodus, a
RetroArch core) or flash it to a cartridge.

**Eleven of the thirteen commands run with nothing but Python**, on
Windows included. Only `build` and `verify` — plus edits written as
`asm` rather than `bytes` — shell out to GNU m68k binutils (`apt install
binutils-m68k-linux-gnu`, or WSL/MSYS2 on Windows). The toolkit says so
explicitly rather than failing obscurely when they're absent.

## Testing it

```
cd toolkit
python -m pytest                                     # 62 tests, no ROM needed
genesis-toolkit selftest "your rom.md" --map maps/nhl94-ue.json
```

`selftest` checks every guarantee end to end against *your* cartridge —
header and checksum, a byte-exact disassemble/reassemble round-trip,
patch application and guard behaviour, checksum repair, an IPS
round-trip, the data map, and that your original file is untouched
afterwards. It takes a couple of seconds and exits non-zero on failure,
so it works in CI.

It cannot tell you a ROM **boots**. That needs an emulator and a human:
build an *unmodified* ROM first (it should be byte-identical, so any
misbehaviour is the toolkit's fault, not your mod's), then apply a mod
with a visible effect — renaming a team shows up on screen — and confirm
you see it.

## What's in here

| | |
|---|---|
| `toolkit/genesis_toolkit/` | the library and `genesis-toolkit` CLI |
| `toolkit/maps/nhl94-ue.json` | data map: all 28 NHL '94 team headers |
| `toolkit/tests/` | 62 tests, incl. a synthetic non-copyrighted fixture ROM |

Capabilities, in rough order of how you'd meet them:

- **Read** a cartridge header, checksum, and 68000 vector table.
- **Disassemble** by recursive descent from the vector table, then
  **reassemble byte-exact** and diff against the original to prove the
  disassembly is faithful.
- **Edit by name** through data maps, instead of memorising offsets.
- **Patch** a ROM from a small JSON mod file, fixing the header checksum.
- **Share** mods as IPS patches rather than modified ROMs.
- **Hunt** for gameplay values with `consts`, which lists code using a
  given immediate.

See [`toolkit/README.md`](toolkit/README.md) for the full command
reference, the mod file format, and the workflow for locating a value
you want to change.

## Design stance: fail loudly

ROM patching is notorious for going wrong *quietly* — you get a ROM that
boots and misbehaves, with nothing to point at. Most of the engineering
here is spent making that impossible, and most of it exists because the
tests caught the toolkit doing exactly what it now refuses to do:

- **Mods carry `expect` guards.** An edit records the bytes it assumes
  are there and refuses to apply otherwise, so a mod aimed at the wrong
  ROM revision is an error naming the address, not silent corruption.
- **Branches can't be written against bare addresses.** GNU as reads
  `bra.w 0x420` as a *displacement*, not a target, and encodes zero — an
  infinite loop, no diagnostic. Rejected outright; write `rom+0x420`.
- **Undefined labels are caught.** With no link step, `as` and `objcopy`
  both exit 0 and write zeros into the unresolved field. The assembler
  step checks for undefined symbols itself.
- **Data maps record their ROM's SHA-256** and warn when read against a
  different image.
- Overlapping edits, out-of-range edits, and anything that would resize
  a cartridge are all errors.

## What's deliberately not here

No ROM, no disassembly output, no extracted game content. Data maps
store *addresses and field names only* — they describe layout, they
don't copy the game. Mods are patches, so they carry your changes and
nothing of the original.

Bring your own ROM; the toolkit does the rest.
