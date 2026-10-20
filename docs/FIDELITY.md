# Fidelity: what counts as evidence

Resident Doom's `main.zs` opens with *"Authoritative sources and
exceptions: docs/FIDELITY.md"* — and that file was never published. The
deviation record stayed in the author's private tree, so anyone
extending the public repo has to re-derive which behaviour is the
original's and which is an adaptation. This file exists so that does not
happen here.

## The one hard rule

`tools/verify.py` must report BIT-PERFECT. A region whose assembly does
not reproduce the cartridge byte for byte is wrong, and the response is
to fix it or remove it. There is no "close enough" state, and nothing in
this repo is allowed to depend on one.

That makes correctness mechanical rather than a matter of judgement:
either the bytes come back identical or they do not.

## What may go in `src/regions.json`

Every region needs an `evidence` field, and `tools/split.py` refuses the
build without one. Evidence is a statement of how the address was
*established*, in descending order of strength:

1. **Executed.** A code/data log from an emulator recorded the CPU
   fetching an opcode at this address while the game ran. This is ground
   truth; nothing beats it.
2. **Named by an instruction.** A reachable instruction names the
   address in an operand — a `bsr` target, or a dispatch table whose base
   a `lea`/`movea.l` loads. Provable by reading the code.
3. **Published by a named source.** Someone else's documented finding,
   cited to where they wrote it down, so it can be checked.

Not evidence, and not acceptable:

- "Recursive descent reached it." Following branches from the vector
  table reaches roughly 4.6% of this cartridge and cannot distinguish a
  real routine from data that happens to decode.
- "It looked like code." A run of plausible pointers is a guess. An
  earlier version of this project scanned for them; it raised apparent
  coverage to 8.9% and raised the share of instructions that would not
  reassemble sevenfold, because much of what it found was data.
- "The checksum still passes." The header checksum is 16 bits. It says
  nothing useful about whether a region is correct.

## Known deviations

None. The build is byte-identical to the cartridge, so by construction
there is nothing to record here yet.

Anything that ever *does* deviate — a macro that assembles differently
on another assembler version, a region kept as data because its encoding
could not be reproduced — gets an entry here naming the address, what
differs, and why it was accepted. An empty section is the goal state,
not an oversight.

## Assembler settings that are load-bearing

- `-no-opt` — without it vasm relaxes `move.l #1,d0` (`203c00000001`) to
  `moveq` (`7001`). Any such relaxation breaks the match.
- `-m68000` — the Genesis CPU. A later model accepts instructions this
  one does not have and encodes some differently.

These are set in `tools/build.py` and covered by
`tests/test_pipeline.py::test_no_opt_keeps_the_original_encoding`, so a
change to either fails the suite rather than silently producing a
lookalike ROM.
