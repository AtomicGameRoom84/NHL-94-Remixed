# Verification record

What has actually been run, and what has not. Claims of "it works" are
worth only as much as the record behind them.

## Verified

- **Toolchain setup.** `tools/setup.py` downloaded vasm 2.0f, checked it
  against the pinned SHA-256 in `tools/toolchain-lock.json`, unpacked it
  with path-escape and link checks, built `vasmm68k_mot`, and installed
  it to `.local/vasm/`. Run on Linux.
- **The byte-exact invariant, empty case.** Synthetic fixture cartridge,
  no regions declared: one `incbin`, rebuild BIT-PERFECT at 16,384 bytes.
- **The byte-exact invariant, carved case.** Same cartridge with a
  34-byte code region replacing part of the blob: still BIT-PERFECT,
  same SHA-1 as the uncarved build.
- **The gate actually fails.** A region whose assembly does not match is
  rejected with the offending offsets, not tolerated.
- **`-no-opt` is load-bearing.** `move.l #1,d0` assembles to
  `203c00000001` with the flag and `7001` without it. Covered by a test.
- **Bad regions are rejected** for missing evidence, overlap,
  running past the end of the cartridge, or naming another revision.
- **Unknown cartridges are rejected** with their own SHA-1 and SHA-256
  printed, so an unsupported revision can be added deliberately.
- **Generated includes cover every byte** of the cartridge; the splitter
  refuses to write a build that does not.
- 10 tests pass.

## Not verified

- **The real NHL '94 cartridge.** No copyrighted ROM exists in this
  environment, so every result above is from the synthetic fixture. The
  pipeline is sound; it has not been run against the actual cartridge.
  That is the first thing to do on a machine that has one.
- **Windows.** Developed and tested on Linux only. `tools/setup.py`
  builds vasm with `make`, which needs a working compiler; on Windows
  that means MSYS2/MinGW or a prebuilt vasm placed on `PATH`.
- **No region has been identified in the real cartridge.**
  `src/regions.json` is empty, which is the correct and intended
  starting state — not a sign of progress.
- **No emulator code/data log has been captured**, so nothing here rests
  on executed-code ground truth yet.

## Earlier work, superseded

A previous iteration disassembled the cartridge by following control
flow from the vector table and reassembled it byte-identically with GNU
`as`. That round-trip was real (1,048,576 bytes, exact match) but the
approach was wrong in three ways, which is why it was replaced:

- It measured how much it could reach (4.63%, or 6.56% with dispatch
  tracing) rather than how much was *known*.
- Its invariant ran the wrong way: it built up a disassembly and checked
  whether it still matched, instead of starting matched and never
  letting that break.
- GNU `as` silently re-encodes instructions, which cost a long tail of
  per-instruction workarounds that `-no-opt` removes outright.

The dispatch tracer from that work survives and produced the table
addresses in `docs/ROM_MAP.md`; one of them independently confirmed a
finding KanedaFr published from IDA.
