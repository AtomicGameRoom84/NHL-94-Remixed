"""Ranking decides what gets worked on, so it has to be right.

Pick a hard routine first and the day goes on one encoding that will not
round-trip. Pick cheap ones first and each lands, which is the whole
reason this ordering exists.
"""
from __future__ import annotations

import json

import pytest

from candidates import ATTEMPT_CAP, rank
from conftest import write_regions

RESET = 0x400          # 8 instructions, 2 branches
SUBROUTINE = 0x418     # 3 instructions, no branches


@pytest.fixture
def ranked(tmp_path, cartridge, lock):
    regions = write_regions(tmp_path / "r.json", [])
    return rank(cartridge, regions, lock, tmp_path / "blocked.json")


def test_cheapest_routine_comes_first(ranked):
    assert [r["at"] for r in ranked][:2] == [f"0x{SUBROUTINE:06x}",
                                             f"0x{RESET:06x}"]


def test_cost_reflects_branches_not_just_size(ranked):
    by_addr = {r["at"]: r for r in ranked}
    small = by_addr[f"0x{SUBROUTINE:06x}"]
    large = by_addr[f"0x{RESET:06x}"]
    assert small["size"] < large["size"]
    assert small["branches"] == 0 and large["branches"] == 2
    assert small["cost"] < large["cost"]


def test_returns_are_not_counted_as_branches(ranked):
    """The subroutine is movem/movem/rts. Counting rts as a branch would
    make every routine look one step more expensive than it is."""
    sub = next(r for r in ranked if r["at"] == f"0x{SUBROUTINE:06x}")
    assert sub["instructions"] == 3
    assert sub["branches"] == 0
    assert sub["terminated"] is True


def test_already_carved_routines_are_not_offered(tmp_path, cartridge, lock):
    regions = write_regions(tmp_path / "r.json", [{
        "at": f"0x{RESET:06x}", "size": 34, "name": "reset handler",
        "source": "tests/fixtures/reset.asm",
        "evidence": "Hand-authored fixture.",
    }])
    assert rank(cartridge, regions, lock, tmp_path / "blocked.json") == []


def test_routine_at_the_attempt_cap_is_held_back(tmp_path, cartridge, lock):
    """Without this the queue livelocks: the cheapest routine is also
    the one that keeps failing, so it is offered forever."""
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps({"routines": {
        f"0x{SUBROUTINE:06x}": {"attempts": ATTEMPT_CAP,
                                "reason": "movem mask will not round-trip"},
    }}))
    out = rank(cartridge, write_regions(tmp_path / "r.json", []), lock, blocked)
    held = [r for r in out if r["held"]]
    assert [r["at"] for r in held] == [f"0x{SUBROUTINE:06x}"]
    assert out[-1]["held"], "a held routine must sort last, not first"
    assert out[0]["at"] == f"0x{RESET:06x}"
    assert "movem" in held[0]["note"]


def test_attempts_below_the_cap_still_offered(tmp_path, cartridge, lock):
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps({"routines": {
        f"0x{SUBROUTINE:06x}": {"attempts": ATTEMPT_CAP - 1, "reason": "trying"},
    }}))
    out = rank(cartridge, write_regions(tmp_path / "r.json", []), lock, blocked)
    assert out[0]["at"] == f"0x{SUBROUTINE:06x}"
    assert not out[0]["held"]


def test_blocked_file_is_optional(tmp_path, cartridge, lock):
    out = rank(cartridge, write_regions(tmp_path / "r.json", []), lock,
               tmp_path / "does-not-exist.json")
    assert out and all(r["attempts"] == 0 for r in out)
