#!/usr/bin/env python3
"""Split, assemble, and prove the result is the cartridge byte for byte.

This is the gate the whole project is built around. It is not a test of
the disassembly's quality -- it is the statement that the disassembly is
*the game* and not a lookalike. Anything less than an exact match means
a region is wrong, and the right response is to fix or remove it, never
to accept a near miss.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import BuildError, assemble  # noqa: E402
from romcheck import DEFAULT_LOCK, RomError, digests, identify  # noqa: E402
from split import split  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def first_differences(a: bytes, b: bytes, limit: int = 10) -> list[int]:
    out = []
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            out.append(i)
            if len(out) == limit:
                break
    return out


def verify(rom_path: Path, regions_path: Path, out_dir: Path,
           assembler: Path | None = None,
           lock_path: Path = DEFAULT_LOCK) -> bool:
    entry = identify(rom_path, lock_path)
    summary = split(rom_path, regions_path, out_dir, lock_path)
    built_path = assemble(ROOT / "src" / "nhl94.asm",
                          out_dir / "nhl94.bin", assembler,
                          include_dir=out_dir)

    original = rom_path.read_bytes()
    built = built_path.read_bytes()
    pct = 100 * summary["code_bytes"] / summary["size"]

    print(f"Cartridge   : {entry['id']} ({entry['title']})")
    print(f"Regions     : {summary['regions']} "
          f"({summary['code_bytes']:,} bytes identified as code, {pct:.2f}%)")

    if len(built) != len(original):
        print(f"SIZE MISMATCH: rebuilt {len(built):,} bytes, "
              f"cartridge {len(original):,} bytes")
        return False
    if built != original:
        bad = first_differences(original, built)
        print(f"BYTE MISMATCH at {len(bad)}+ offsets, first: "
              + ", ".join(f"0x{i:06x}" for i in bad))
        print("A region is wrong. Remove it, or fix its assembly until this "
              "passes -- do not commit a near miss.")
        return False

    print(f"Rebuilt     : {len(built):,} bytes")
    print(f"sha1        : {digests(built)['sha1']}")
    print("BIT-PERFECT: the rebuild is the cartridge, byte for byte.")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom", default=str(ROOT / "rom" / "nhl94.md"))
    p.add_argument("--regions", default=str(ROOT / "src" / "regions.json"))
    p.add_argument("--out", default=str(ROOT / "build"))
    p.add_argument("--assembler")
    p.add_argument("--lock", default=str(DEFAULT_LOCK),
                   help="rom-lock.json to identify the cartridge against")
    a = p.parse_args()
    try:
        ok = verify(Path(a.rom), Path(a.regions), Path(a.out),
                    Path(a.assembler) if a.assembler else None,
                    Path(a.lock))
    except (RomError, BuildError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
