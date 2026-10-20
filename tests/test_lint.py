"""The audit is only worth something if something enforces it."""
from __future__ import annotations

import re

import pytest

from lint import AUTO_NAME, CARTRIDGE_SUFFIXES, SECRET_PATTERNS, check


def test_repo_is_clean():
    fails, _ = check()
    assert fails == [], "\n".join(fails)


@pytest.mark.parametrize("label", [
    "sub_0117b2",   # this project's own tracer emits lowercase
    "sub_117AC",    # IDA emits uppercase
    "off_11AF4",
    "unk_11B92",
    "loc_1A470",
    "FUN_00401000",  # Ghidra
    "DAT_00be98e4",
])
def test_raw_decompiler_names_are_recognised(label):
    """A region named after its address has been located, not
    understood. Committing one as code defeats the requirement that
    every region carry a real name and its evidence."""
    assert AUTO_NAME.search(label), label


@pytest.mark.parametrize("ok", [
    "read_joypad", "sub_total", "offset_table", "dispatch_table",
    "0x011AF4",            # a plain address in prose is how findings stay checkable
])
def test_real_names_and_addresses_are_not_flagged(ok):
    assert not AUTO_NAME.search(ok), ok


def test_cartridge_extensions_are_refused():
    for suffix in (".bin", ".gen", ".smd", ".ips", ".inc"):
        assert suffix in CARTRIDGE_SUFFIXES


def test_secret_patterns_match_their_own_shapes():
    # Every sample is assembled at runtime so no complete credential
    # shape appears as a literal in this file. The linter reads tracked
    # files, this file is tracked, and a literal here would make the
    # suite fail on its own test data -- which is exactly what happened
    # the first time, and only in CI: the test passed locally because
    # the file was not yet added, and `git ls-files` cannot see an
    # untracked file.
    samples = {
        "Anthropic key": "sk-ant-" + "a" * 24,
        "AWS key id": "AKIA" + "A" * 16,
        "private key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
    }
    by_label = dict(SECRET_PATTERNS)
    for label, sample in samples.items():
        assert by_label[label].search(sample), label
