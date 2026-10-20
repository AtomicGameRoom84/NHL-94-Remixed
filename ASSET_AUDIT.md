# Publication audit

What this repository publishes, and what it refuses to. The structure
follows [Resident Doom](https://github.com/Drelvak/Resident-Doom)'s
audit, which this project is modelled on.

| Classification | Material | Publication treatment |
| --- | --- | --- |
| Project work | Splitter, builder, verifier, ROM identification, disassembly and mod tooling, tests, docs | Source only, PolyForm Noncommercial 1.0.0 |
| Cartridge data | The NHL '94 ROM, and every byte carved out of it (`build/data/*.bin`, `build/regions.inc`, any rebuilt image) | Excluded. Generated locally from the user's own cartridge; never committed, never released |
| Identified code | Assembly in `src/code/` that reproduces cartridge bytes exactly | **Not yet published, and the open question below** |
| Toolchain | vasm | Not vendored. Fetched by `tools/setup.py` against a pinned SHA-256 and built locally |
| Third-party findings | Addresses published by others | Cited to the source in `docs/ROM_MAP.md`; their files not redistributed |
| Test material | Synthetic fixture cartridge and its reset handler | Published. Hand-authored for this suite, derived from no game |
| Local state | Fetched archives, build output, saves, logs, venvs | Excluded by `.gitignore` |

No ROM, ROM-derived blob, rebuilt image, or extracted asset is
intentionally published. `rom/` holds only its own instructions.

## The `.md` collision

An asset-free repo normally blanket-ignores the data extension — Resident
Doom can safely ignore `*.wad`. A Genesis ROM and a Markdown document
both use `.md`, so that rule would untrack this project's own
documentation. ROMs are excluded by location (`rom/*`) plus the other
cartridge extensions (`.bin`, `.gen`, `.smd`, `.32x`, `.68k`) instead.
Worth knowing before copying a `.gitignore` from another console's
project.

## Open question: is a matching disassembly itself distributable?

Honestly, unresolved. A byte-exact disassembly is a mechanical
transformation of copyrighted code: run the assembler and the original
comes back. Different projects answer this differently — some publish
the assembly, some publish only a splitter plus labels and let the user
generate the rest.

This project currently publishes no identified code, so the question is
not yet live. Before `src/code/` gets its first file, decide which model
to follow. The safer option, and the one the splitter is already built
for, is to commit labels and structure while leaving the bytes to come
from the user's own cartridge.

Following Resident Doom's example of saying so plainly rather than
implying more certainty than exists: no claim of legally guaranteed
safety is made here. Reverse-engineering a commercial game is contested
ground, and nothing in this repository changes that.
