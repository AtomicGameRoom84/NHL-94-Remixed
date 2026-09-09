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
- `genesis_toolkit/cli.py` -- `genesis-toolkit header|vectors|disasm|build|verify`.

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

Run the tests with `python -m pytest` from this directory (requires
`m68k-linux-gnu-as`/`objcopy`, e.g. `apt install binutils-m68k-linux-gnu`,
for the round-trip tests -- they're skipped automatically if that's not
installed).
