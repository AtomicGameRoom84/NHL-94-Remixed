# Third-party material

## Build dependency, fetched not vendored

**vasm** 2.0f — `vasmm68k_mot`, Volker Barthelmann and Frank Wille.
<http://sun.hasenbraten.de/vasm/>

Downloaded by `tools/setup.py` against the SHA-256 pinned in
`tools/toolchain-lock.json` and built locally. No binary is committed
here. vasm is free for non-commercial and commercial use under its own
terms; see the `COPYING` file in its distribution.

Chosen over GNU `as` because `-no-opt` disables the instruction
relaxation that makes byte-exact reassembly impossible, and over AS
(Alfred Arnold's macroassembler, the Sonic Retro disassemblies' choice)
only because AS's host was unreachable from the build environment. AS
with `zeroOffsetOptimization = 0` is an equally valid choice.

## Python packages

- **capstone** — disassembly engine used by the mod tooling in
  `toolkit/`. BSD 3-clause.
- **pytest** — test runner. MIT.

## Published findings cited, not redistributed

- **KanedaFr**, NHL '94 disassembly notes and 6-button patch —
  <https://gendev.spritesmind.net/page-nhl94.html>. Addresses cited in
  `docs/ROM_MAP.md`. Their IDA database and patches are not included here.
- **Kodewerx**, RAM tracing guide —
  <https://www.kodewerx.org/forum/viewtopic.php?p=35048>. Method and the
  game-clock address cited in `docs/RAM_MAP.md`.
- **Resident Doom**, Drelvak — <https://github.com/Drelvak/Resident-Doom>.
  The audit, pinned-input and generate-locally structure this project
  follows. No code taken.
- **kid-chameleon-disasm**, Sonic Retro —
  <https://github.com/sonicretro/kid-chameleon-disasm>. The
  split-and-rebuild model for a Genesis matching disassembly.

## Not included and never will be

NHL '94 is © 1993 Electronic Arts. The cartridge, any dump of it, and
anything carved out of one are excluded from this repository. You supply
your own legally obtained copy.
