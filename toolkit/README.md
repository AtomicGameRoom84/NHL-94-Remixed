# genesis-toolkit

A generic disassembly/reassembly toolkit for Sega Genesis / Mega Drive
ROMs. Nothing in this package is specific to any one game -- every tool
here takes a ROM path as input and works off the cartridge header and
68000 vector-table format shared by every Genesis title, so it's meant
to be reused across games, not just the one it was first built against.

**No ROM files live in this repository.** The toolkit operates on a ROM
you supply at the command line; it never bundles, commits, or requires
a copy of any commercial game. Its own test suite ships a tiny,
entirely hand-authored fixture ROM (`tests/fixtures/make_fixture.py`) --
not derived from or resembling any real game -- purely to exercise the
header/vector/disassembly/reassembly pipeline end to end.

## What's here

- `genesis_toolkit/header.py` -- parses the standard cartridge header
  (title, serial, region, ROM/RAM ranges, checksum) and verifies the
  Genesis checksum algorithm.
- `genesis_toolkit/vectors.py` -- reads the 68000 exception vector
  table and picks out vectors that plausibly point at ROM code, to seed
  disassembly.
- `genesis_toolkit/disasm.py` -- a recursive-descent 68000 disassembler
  (via capstone) that follows control flow from a set of entry points,
  rather than blindly decoding every byte linearly. Anything never
  reached by that walk is left as data, which is what keeps the output
  re-assemblable instead of degrading into garbage the moment a linear
  sweep wanders into a data/graphics/audio blob.
- `genesis_toolkit/asmgen.py` -- translates capstone's M68K disassembly
  text into GNU-as-compatible syntax. This is where most of the actual
  engineering is: capstone's Motorola-dialect printer and GNU as's
  parser disagree on several things (see the module docstring for the
  full list -- hex immediate syntax, how PC-relative branch/addressing
  targets have to be real positional labels rather than literals or
  `.set` constants, an EXG size-suffix quirk, a MOVEQ range-check
  quirk, and GAS's undocumented but deterministic habit of silently
  re-encoding `move.l #small,Dn` as the shorter MOVEQ form).
- `genesis_toolkit/build.py` -- reassembles generated `.s` files with
  `m68k-linux-gnu-as`/`objcopy` and diffs the result against a
  reference ROM. Includes a "patch and reconcile" loop: any instruction
  GAS rejects outright, or accepts but re-encodes differently than the
  original ROM's bytes, gets replaced with a raw `.byte` dump of the
  original bytes so the rest of the file can still be verified. The
  addresses that needed patching are exactly the punch list for
  improving the translator further.
- `genesis_toolkit/patch.py` -- the mod layer: a mod is a small JSON
  file of edits, not a modified ROM. Applies edits, fixes up the header
  checksum, and reads/writes IPS patches.
- `genesis_toolkit/datamap.py` -- named fields: give addresses names and
  types once, then edit by name instead of by offset.
- `genesis_toolkit/selftest.py` -- runs every guarantee end to end
  against a real ROM.
- `genesis_toolkit/cli.py` -- the `genesis-toolkit` command:
  `header`, `vectors`, `disasm`, `build`, `verify`, `patch`,
  `fix-checksum`, `ips-create`, `ips-apply`, `map-list`, `map-set`,
  `consts`, `selftest`.

## Usage

```
pip install -e .
genesis-toolkit header  path/to/some.md
genesis-toolkit vectors path/to/some.md
genesis-toolkit disasm  path/to/some.md out.s
genesis-toolkit verify  path/to/some.md out.s
```

`verify` assembles `out.s` and diffs it byte-for-byte against the ROM.
An `EXACT MATCH` means the disassembly (after any reported patches) is
a faithful, re-assemblable representation of that ROM.

## Modding

A mod is a JSON file. Keeping mods as patches rather than edited ROM
images means they're small, diffable, reviewable, and carry no
copyrighted content -- so they can live in a repo while the ROM never
does.

```json
{
  "name": "faster-skating",
  "edits": [
    {"at": "0x78b0", "asm": "\tmove.w #0x28, d0", "expect": "303c001e",
     "note": "was move.w #0x1e,d0"},
    {"at": "0x9120", "bytes": "4e714e71", "note": "nop out the check"}
  ]
}
```

```
genesis-toolkit patch      orig.md mod.json modded.md   # apply
genesis-toolkit ips-create orig.md modded.md mod.ips    # share as a patch
genesis-toolkit ips-apply  orig.md mod.ips  modded.md   # someone else applies it
```

Then load `modded.md` in any emulator (BlastEm, Genesis Plus GX,
Exodus, a RetroArch core) or flash it to a cart.

### Data maps: editing by name instead of by offset

A *data map* gives names, addresses and types to interesting bytes in a
game -- the machine-readable form of the ROM maps romhacking
communities have always traded. `maps/nhl94-ue.json` ships one for NHL
'94, covering all 28 team headers, derived from the ROM and verified
against it.

```
genesis-toolkit map-list rom.md maps/nhl94-ue.json --filter TOR
genesis-toolkit map-set  rom.md maps/nhl94-ue.json mymod.json \
    --set "team.TOR.nickname=Blue Jays"
genesis-toolkit patch    rom.md mymod.json modded.md
```

A map holds *addresses*, never the values found there, so it describes
layout rather than copying the game's content. It records the SHA-256 of
the ROM it was derived from and warns when read against a different one,
since an address that's right for one dump is meaningless in another.
Generated mods get their `expect` guards filled in automatically, so
they're safe by construction.

Writing a string writes the text and its terminator *only*, never
padding out the rest of the slot: trailing bytes in these slots are
structural (NHL '94 stores strings as `[size byte][text][NUL][pad]`, so
the bytes after one string include the size prefix of the next), and
blanking them would corrupt the record even though the text looked fine.

### Finding a value to edit

For anything not yet mapped -- a speed constant, a scoring rule -- the
workflow is:

1. Find the value live in an emulator's RAM search while playing.
2. Break on writes to that RAM address to find the code that sets it.
3. `genesis-toolkit consts rom.md 5 --mnemonic cmp` lists every
   instruction using that immediate, to cross-reference against the
   address your breakpoint found.
4. Add it to a data map, and it's a named field from then on.

`consts` only searches code the disassembler has reached, so it finds
candidates rather than answers -- confirm with a breakpoint before
editing.

Three things the patcher does so an edit can't quietly go wrong:

- **`expect` guards.** An edit records the bytes it assumes are already
  there and refuses to apply if they differ. That turns "this mod was
  written against another ROM revision" -- the failure mode ROM patches
  are infamous for -- into an error naming the address, instead of
  silent corruption.
- **Edits are assembled at their real address**, so a branch or a
  `(d16,PC)` operand resolves against where the code actually sits. Two
  labels are in scope: `rom` is the start of the cartridge (`rom+0x420`
  is absolute ROM address 0x420) and `here` is the edit site. Writing a
  branch against a bare literal (`bra.w 0x420`) is rejected outright,
  because GNU as reads that as a displacement and encodes a *zero*
  target with no diagnostic.
- **Overlapping edits, out-of-range edits, and stale checksums** are all
  caught. Edits can never resize the cartridge.

## Honest scope

Recursive descent only finds code reached from the vector table and any
extra entry points you supply -- on a real commercial game, most code
is reached indirectly (via jump tables, engine dispatch, etc.) and
won't be found this way without further work (tracing jump tables,
annotating known routine addresses, iterating on what a `verify` pass
reports as data that should have been code). That iterative refinement
-- exactly how long-running disassembly projects for other consoles are
built over months, not one sitting -- is what this toolkit is meant to
support, not replace.

## Verifying it against your own ROM

```
genesis-toolkit selftest path/to/some.md --map maps/nhl94-ue.json
```

Runs every machine-checkable guarantee end to end -- header/checksum, a
byte-exact disassemble/reassemble round-trip, patch application and
`expect` guard behaviour, checksum repair, an IPS round-trip, the data
map, and that the original file is untouched afterwards. Exits non-zero
on failure. It cannot prove a ROM boots; that needs an emulator.

Run the unit tests with `pip install -e ".[test]"` then `python -m pytest`
from this directory (the round-trip tests additionally require
`m68k-linux-gnu-as`/`objcopy`, e.g. `apt install binutils-m68k-linux-gnu`,
for the round-trip tests -- they're skipped automatically if that's not
installed).
