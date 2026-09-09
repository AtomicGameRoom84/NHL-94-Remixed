"""Command-line entry point for genesis_toolkit.

    genesis-toolkit header  <rom>
    genesis-toolkit vectors <rom>
    genesis-toolkit disasm  <rom> <out.s>
    genesis-toolkit build   <in.s> <out.bin>
    genesis-toolkit verify  <rom> <out.s>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import build as build_mod
from . import header as header_mod
from . import patch as patch_mod
from . import vectors as vectors_mod
from .disasm import linear_map, recursive_descent
from .asmgen import emit_asm


def _load(path: str) -> bytes:
    return Path(path).read_bytes()


def cmd_header(args: argparse.Namespace) -> int:
    rom = _load(args.rom)
    h = header_mod.parse_header(rom)
    print(f"Console name     : {h.console_name!r}")
    print(f"Copyright/release: {h.copyright_release!r}")
    print(f"Domestic title   : {h.domestic_title!r}")
    print(f"Overseas title   : {h.overseas_title!r}")
    print(f"Serial number    : {h.serial_number!r}")
    print(f"Checksum         : declared=0x{h.declared_checksum:04x} "
          f"computed=0x{h.computed_checksum:04x} ok={h.checksum_ok}")
    print(f"Device support   : {h.device_support!r}")
    print(f"ROM range        : 0x{h.rom_start:08x}-0x{h.rom_end:08x}")
    print(f"RAM range        : 0x{h.ram_start:08x}-0x{h.ram_end:08x}")
    print(f"Extra memory     : {h.extra_memory!r}")
    print(f"Modem support    : {h.modem_support!r}")
    print(f"Region codes     : {h.region_codes!r}")
    return 0


def cmd_vectors(args: argparse.Namespace) -> int:
    rom = _load(args.rom)
    for e in vectors_mod.parse_vector_table(rom):
        print(f"{e.index:2d} {e.name:26s} 0x{e.address:08x}")
    return 0


def _disassemble(rom: bytes):
    entry_points = [("reset", int.from_bytes(rom[4:8], "big"))]
    entry_points += [
        (name, addr) for name, addr in vectors_mod.code_entry_points(rom)
        if name != "reset_pc"
    ]
    result = recursive_descent(rom, entry_points)
    spans = linear_map(result, rom)
    return entry_points, result, spans


def cmd_disasm(args: argparse.Namespace) -> int:
    rom = _load(args.rom)
    entry_points, result, spans = _disassemble(rom)
    asm_text = emit_asm(spans, entry_points, len(rom))
    Path(args.out).write_text(asm_text)

    code_bytes = sum(s.size for s in spans if hasattr(s, "mnemonic"))
    data_bytes = sum(s.size for s in spans if not hasattr(s, "mnemonic"))
    print(f"Entry points found : {len(entry_points)}")
    print(f"Instructions       : {len(result.instructions)} ({code_bytes} bytes)")
    print(f"Data bytes         : {data_bytes}")
    print(f"Decode failures    : {len(result.decode_failures)}")
    print(f"Wrote              : {args.out}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    try:
        build_mod.assemble(Path(args.asm), Path(args.out))
    except build_mod.AssembleError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Wrote {args.out}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    rom = _load(args.rom)
    out_bin = Path(args.asm).with_suffix(".verify.bin")
    try:
        patched = build_mod.assemble_and_reconcile(rom, Path(args.asm), out_bin)
    except build_mod.AssembleError as e:
        print(str(e), file=sys.stderr)
        return 1
    rebuilt = out_bin.read_bytes()
    report = build_mod.verify(rom, rebuilt)
    if patched:
        rejects = [(ln, a) for reason, ln, a in patched if reason == "gas-reject"]
        mismatches = [(ln, a) for reason, ln, a in patched if reason == "byte-mismatch"]
        print(f"NOTE: {len(patched)} instruction(s) could not be reproduced by the "
              f"current translator and were patched with raw byte dumps (so the "
              f"rest of the file could still be verified). These addresses are the "
              f"punch list for improving the translator:")
        if rejects:
            print(f"  GAS rejected the generated syntax outright ({len(rejects)}):")
            for _, addr in rejects:
                print(f"    0x{addr:06x}")
        if mismatches:
            print(f"  GAS accepted it but re-encoded it differently ({len(mismatches)}):")
            for _, addr in mismatches:
                print(f"    0x{addr:06x}")
    print(report.summary())
    return 0 if report.exact_match else 2


def cmd_patch(args: argparse.Namespace) -> int:
    rom = _load(args.rom)
    try:
        name, edits = patch_mod.load_mod(Path(args.mod))
        patched = patch_mod.apply_edits(rom, edits,
                                        fix_checksum=not args.no_fix_checksum)
    except patch_mod.PatchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    Path(args.out).write_bytes(patched)

    print(f"Mod            : {name}")
    for edit in edits:
        note = f"  {edit.note}" if edit.note else ""
        print(f"  0x{edit.address:06x}  {len(edit.data):2d} bytes  "
              f"{edit.data.hex()}{note}")
    changed = sum(1 for a, b in zip(rom, patched) if a != b)
    print(f"Bytes changed  : {changed}")
    print(f"Wrote          : {args.out}")
    return 0


def cmd_fix_checksum(args: argparse.Namespace) -> int:
    rom = _load(args.rom)
    before = header_mod.parse_header(rom)
    fixed = patch_mod.fix_header_checksum(rom)
    after = header_mod.parse_header(fixed)
    Path(args.out).write_bytes(fixed)
    print(f"Checksum: 0x{before.declared_checksum:04x} -> 0x{after.declared_checksum:04x} "
          f"(computed 0x{after.computed_checksum:04x})")
    print(f"Wrote   : {args.out}")
    return 0


def cmd_ips_create(args: argparse.Namespace) -> int:
    try:
        data = patch_mod.create_ips(_load(args.original), _load(args.modified))
    except patch_mod.PatchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    Path(args.out).write_bytes(data)
    print(f"Wrote {args.out} ({len(data)} bytes)")
    return 0


def cmd_ips_apply(args: argparse.Namespace) -> int:
    try:
        data = patch_mod.apply_ips(_load(args.rom), _load(args.patch))
    except patch_mod.PatchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    Path(args.out).write_bytes(data)
    print(f"Wrote {args.out} ({len(data)} bytes)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="genesis-toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("header", help="parse and print the cartridge header")
    p.add_argument("rom")
    p.set_defaults(func=cmd_header)

    p = sub.add_parser("vectors", help="print the 68000 exception vector table")
    p.add_argument("rom")
    p.set_defaults(func=cmd_vectors)

    p = sub.add_parser("disasm", help="recursive-descent disassemble a ROM to .s")
    p.add_argument("rom")
    p.add_argument("out")
    p.set_defaults(func=cmd_disasm)

    p = sub.add_parser("build", help="assemble a .s file to a raw binary")
    p.add_argument("asm")
    p.add_argument("out")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("verify", help="assemble a .s file and diff it against a ROM")
    p.add_argument("rom")
    p.add_argument("asm")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("patch", help="apply a JSON mod file to a ROM")
    p.add_argument("rom")
    p.add_argument("mod", help="mod file describing the edits")
    p.add_argument("out", help="patched ROM to write")
    p.add_argument("--no-fix-checksum", action="store_true",
                   help="leave the header checksum alone after patching")
    p.set_defaults(func=cmd_patch)

    p = sub.add_parser("fix-checksum", help="recompute the header checksum")
    p.add_argument("rom")
    p.add_argument("out")
    p.set_defaults(func=cmd_fix_checksum)

    p = sub.add_parser("ips-create", help="build an IPS patch from two ROMs")
    p.add_argument("original")
    p.add_argument("modified")
    p.add_argument("out")
    p.set_defaults(func=cmd_ips_create)

    p = sub.add_parser("ips-apply", help="apply an IPS patch to a ROM")
    p.add_argument("rom")
    p.add_argument("patch")
    p.add_argument("out")
    p.set_defaults(func=cmd_ips_apply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
