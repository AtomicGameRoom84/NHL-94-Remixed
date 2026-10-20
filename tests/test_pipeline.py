"""The build either reproduces the cartridge exactly or it fails.

Everything else in this project is commentary on that one property, so
these tests exercise it directly: the empty case, the carved case, and
each way a bad region is supposed to be caught rather than tolerated.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import ROOT, write_regions
from romcheck import RomError, identify
from split import split
from verify import verify

GOOD_REGION = {
    "at": "0x000400", "size": 34, "name": "reset handler + subroutine",
    "source": "tests/fixtures/reset.asm",
    "evidence": "Hand-authored fixture; offsets set by make_fixture.py.",
}


def test_empty_regions_rebuild_the_cartridge(tmp_path, cartridge, lock, assembler):
    """Day one, nothing understood: the whole ROM is one incbin and the
    rebuild matches. This is what makes the invariant free to adopt."""
    regions = write_regions(tmp_path / "r.json", [])
    assert verify(cartridge, regions, tmp_path / "build", assembler, lock)


def test_carved_region_still_rebuilds_the_cartridge(tmp_path, cartridge, lock, assembler):
    """The real test: assembly replaced a slice of the blob and the ROM
    is still identical, so the assembly *is* those bytes."""
    regions = write_regions(tmp_path / "r.json", [GOOD_REGION])
    assert verify(cartridge, regions, tmp_path / "build", assembler, lock)


def test_wrong_region_is_caught(tmp_path, cartridge, lock, assembler):
    """A region whose assembly does not match must fail the gate. If this
    ever passes, every other guarantee here is worthless."""
    wrong = ROOT / "tests" / "fixtures" / "wrong.asm"
    wrong.write_text("\tmoveq\t#0,d0\n" * 17)      # 34 bytes, wrong bytes
    try:
        regions = write_regions(tmp_path / "r.json",
                                [{**GOOD_REGION, "source": "tests/fixtures/wrong.asm"}])
        assert not verify(cartridge, regions, tmp_path / "build", assembler, lock)
    finally:
        wrong.unlink()


def test_region_without_evidence_is_rejected(tmp_path, cartridge, lock):
    region = {k: v for k, v in GOOD_REGION.items() if k != "evidence"}
    regions = write_regions(tmp_path / "r.json", [region])
    with pytest.raises(RomError, match="evidence"):
        split(cartridge, regions, tmp_path / "build", lock)


def test_overlapping_regions_are_rejected(tmp_path, cartridge, lock):
    regions = write_regions(tmp_path / "r.json", [
        GOOD_REGION,
        {**GOOD_REGION, "at": "0x000410", "name": "overlaps the first"},
    ])
    with pytest.raises(RomError, match="inside the region"):
        split(cartridge, regions, tmp_path / "build", lock)


def test_region_past_the_end_is_rejected(tmp_path, cartridge, lock):
    regions = write_regions(tmp_path / "r.json",
                            [{**GOOD_REGION, "at": "0x003ff0", "size": 64}])
    with pytest.raises(RomError, match="past the end"):
        split(cartridge, regions, tmp_path / "build", lock)


def test_regions_for_another_revision_are_rejected(tmp_path, cartridge, lock):
    """Addresses are revision-specific. Silently building one revision's
    regions against another is how a ROM hack half-applies."""
    regions = write_regions(tmp_path / "r.json", [], rom="some-other-revision")
    with pytest.raises(RomError, match="revision-specific"):
        split(cartridge, regions, tmp_path / "build", lock)


def test_unknown_cartridge_is_rejected_with_its_hashes(tmp_path, lock):
    impostor = tmp_path / "not-a-rom.md"
    impostor.write_bytes(b"\x00" * 2048)
    with pytest.raises(RomError) as excinfo:
        identify(impostor, lock)
    message = str(excinfo.value)
    assert "sha256" in message and "add the digests" in message


def test_generated_includes_cover_every_byte(tmp_path, cartridge, lock):
    regions = write_regions(tmp_path / "r.json", [GOOD_REGION])
    summary = split(cartridge, regions, tmp_path / "build", lock)
    blobs = sorted((tmp_path / "build" / "data").glob("*.bin"))
    total = sum(b.stat().st_size for b in blobs) + summary["code_bytes"]
    assert total == cartridge.stat().st_size


def test_no_opt_keeps_the_original_encoding(tmp_path, assembler):
    """vasm relaxes move.l #1,d0 (6 bytes) to moveq (2 bytes) unless
    -no-opt is given. That single flag is the difference between a
    matching build and a lookalike, so it is worth a test of its own."""
    from build import assemble
    source = tmp_path / "relax.asm"
    source.write_text("\torg\t0\n\tmove.l\t#1,d0\n")
    out = assemble(source, tmp_path / "relax.bin", assembler)
    assert out.read_bytes() == bytes.fromhex("203c00000001")
