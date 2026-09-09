"""End-to-end validation of the toolkit against a real ROM.

`pytest` proves the code behaves on a synthetic fixture. This proves the
same guarantees hold for *your* cartridge, which is the thing you
actually care about before trusting a patched ROM:

- the ROM parses and its checksum is self-consistent
- disassembling and reassembling it reproduces it byte for byte
- a patch round-trips, guards fire, and the checksum is repaired
- an IPS patch reproduces the modified image exactly
- the original file is byte-identical afterwards

The one guarantee nothing here can give you is that a ROM *boots*.
That needs an emulator and a human; see the README.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import build as build_mod
from . import datamap as datamap_mod
from . import patch as patch_mod
from .asmgen import emit_asm
from .disasm import linear_map, recursive_descent
from .header import parse_header
from .vectors import code_entry_points

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclass
class Result:
    checks: list[tuple[str, str, str]] = field(default_factory=list)

    def record(self, status: str, name: str, detail: str = "") -> None:
        self.checks.append((status, name, detail))

    @property
    def failed(self) -> int:
        return sum(1 for status, _, _ in self.checks if status == FAIL)

    @property
    def skipped(self) -> int:
        return sum(1 for status, _, _ in self.checks if status == SKIP)


def _disassemble(rom: bytes):
    entry_points = [("reset", int.from_bytes(rom[4:8], "big"))]
    entry_points += [(n, a) for n, a in code_entry_points(rom) if n != "reset_pc"]
    result = recursive_descent(rom, entry_points)
    return entry_points, result, linear_map(result, rom)


def run(rom_path: Path, map_path: Path | None = None,
        workdir: Path | None = None) -> Result:
    out = Result()
    rom = rom_path.read_bytes()
    digest_before = hashlib.sha256(rom).hexdigest()
    workdir = workdir or rom_path.parent

    # --- header -------------------------------------------------------
    try:
        header = parse_header(rom)
        detail = (f"{header.domestic_title.strip()!r} "
                  f"region={header.region_codes!r} {len(rom)} bytes")
        if header.checksum_ok:
            out.record(PASS, "header parses, checksum self-consistent", detail)
        else:
            out.record(FAIL, "header checksum mismatch",
                       f"declared 0x{header.declared_checksum:04x} != "
                       f"computed 0x{header.computed_checksum:04x}")
    except Exception as e:
        out.record(FAIL, "header parses", str(e))

    # --- disassemble / reassemble ------------------------------------
    try:
        entry_points, disasm_result, spans = _disassemble(rom)
        asm_path = workdir / "selftest.s"
        asm_path.write_text(emit_asm(spans, entry_points, len(rom)))
        out.record(PASS, "disassembles",
                   f"{len(disasm_result.instructions)} instructions from "
                   f"{len(entry_points)} entry points")
        try:
            bin_path = workdir / "selftest.bin"
            patched = build_mod.assemble_and_reconcile(rom, asm_path, bin_path)
            rebuilt = bin_path.read_bytes()
            report = build_mod.verify(rom, rebuilt)
            if report.exact_match:
                out.record(PASS, "reassembles byte-exact",
                           f"{len(patched)} instruction(s) needed raw-byte fallback")
            else:
                out.record(FAIL, "reassembles byte-exact", report.summary())
        except build_mod.ToolchainMissing:
            out.record(SKIP, "reassembles byte-exact",
                       "GNU m68k binutils not installed")
        finally:
            for p in (workdir / "selftest.s", workdir / "selftest.bin",
                      workdir / "selftest.verify.bin"):
                p.unlink(missing_ok=True)
    except Exception as e:
        out.record(FAIL, "disassembles", str(e))

    # --- patch round-trip --------------------------------------------
    try:
        # Rewrite some bytes with different ones, then check the image
        # changed exactly there and the checksum was repaired.
        at = 0x200
        original_bytes = rom[at:at + 4]
        new_bytes = bytes(b ^ 0xFF for b in original_bytes)
        edit = patch_mod.Edit(address=at, data=new_bytes,
                              expect=original_bytes, note="selftest")
        modified = patch_mod.apply_edits(rom, [edit])
        changed = [i for i in range(len(rom)) if rom[i] != modified[i]]
        expected = set(range(at, at + 4)) | {0x18E, 0x18F}
        if set(changed) <= expected and modified[at:at + 4] == new_bytes:
            out.record(PASS, "patch writes only where told",
                       f"{len(changed)} bytes changed (incl. checksum)")
        else:
            out.record(FAIL, "patch writes only where told",
                       f"unexpected changes at {changed[:8]}")
        if parse_header(modified).checksum_ok:
            out.record(PASS, "checksum repaired after patching")
        else:
            out.record(FAIL, "checksum repaired after patching")

        # The guard must reject the same edit against the patched image.
        try:
            patch_mod.apply_edits(modified, [edit])
            out.record(FAIL, "expect guard rejects the wrong ROM",
                       "edit applied when it should have been refused")
        except patch_mod.PatchError:
            out.record(PASS, "expect guard rejects the wrong ROM")

        ips = patch_mod.create_ips(rom, modified)
        if patch_mod.apply_ips(rom, ips) == modified:
            out.record(PASS, "IPS patch reproduces the modified ROM",
                       f"{len(ips)} byte patch")
        else:
            out.record(FAIL, "IPS patch reproduces the modified ROM")
    except Exception as e:
        out.record(FAIL, "patch round-trip", str(e))

    # --- optional data map -------------------------------------------
    if map_path is not None:
        try:
            dmap = datamap_mod.load_map(map_path)
            warning = datamap_mod.check_rom_matches(dmap, rom)
            unreadable = []
            for f in dmap.fields:
                try:
                    datamap_mod.read_field(rom, f)
                except patch_mod.PatchError:
                    unreadable.append(f.name)
            if unreadable:
                out.record(FAIL, "every mapped field reads",
                           f"{len(unreadable)} unreadable, e.g. {unreadable[:3]}")
            elif warning:
                out.record(FAIL, "data map matches this ROM", warning)
            else:
                out.record(PASS, "data map matches this ROM",
                           f"{len(dmap.fields)} fields, hash verified")
        except Exception as e:
            out.record(FAIL, "data map loads", str(e))

    # --- the original must be untouched ------------------------------
    digest_after = hashlib.sha256(rom_path.read_bytes()).hexdigest()
    if digest_after == digest_before:
        out.record(PASS, "original ROM file untouched", digest_after[:16] + "...")
    else:
        out.record(FAIL, "original ROM file untouched",
                   "the file on disk changed during this run")
    return out
