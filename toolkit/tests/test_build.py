"""Regression tests for the assemble/verify safety nets."""
import shutil
from pathlib import Path

import pytest

from genesis_toolkit import build as build_mod


def _has_m68k_as() -> bool:
    return shutil.which(build_mod.AS) is not None


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_undefined_symbol_is_an_error_not_silent_zeros(tmp_path: Path):
    # Without a link step nothing catches an undefined symbol: `as` and
    # `objcopy` both succeed and the field is written as zeros. assemble()
    # has to reject it rather than hand back a quietly corrupt binary.
    asm = tmp_path / "undef.s"
    asm.write_text("\t.org 0\nreset:\n\tbsr.w\tnever_defined\n\tnop\n")
    with pytest.raises(build_mod.AssembleError, match="undefined symbol"):
        build_mod.assemble(asm, tmp_path / "out.bin")


@pytest.mark.skipif(not _has_m68k_as(), reason="m68k-linux-gnu-as not installed")
def test_defined_symbol_assembles_cleanly(tmp_path: Path):
    asm = tmp_path / "ok.s"
    asm.write_text("\t.org 0\nreset:\n\tnop\ntarget:\n\tbra.w\ttarget\n")
    out = tmp_path / "out.bin"
    build_mod.assemble(asm, out)
    assert out.read_bytes() == bytes.fromhex("4e716000fffe")


def test_missing_toolchain_explains_itself(tmp_path: Path, monkeypatch):
    # Most of the toolkit is pure Python; only the assembly-backed
    # commands need binutils. A bare FileNotFoundError would hide that.
    monkeypatch.setattr(build_mod, "AS", "definitely-not-installed-m68k-as")
    asm = tmp_path / "x.s"
    asm.write_text("\t.org 0\n\tnop\n")
    with pytest.raises(build_mod.ToolchainMissing, match="pure Python"):
        build_mod.assemble(asm, tmp_path / "out.bin")


def test_verify_reports_exact_match():
    report = build_mod.verify(b"abcd", b"abcd")
    assert report.exact_match
    assert "EXACT MATCH" in report.summary()


def test_verify_reports_first_mismatch():
    report = build_mod.verify(b"abcd", b"abXd")
    assert not report.exact_match
    assert report.first_mismatch == 2
    assert report.matched_bytes == 3
