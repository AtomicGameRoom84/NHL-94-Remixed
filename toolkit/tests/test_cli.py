"""A mistyped path or a wrong working directory is the most common
first-run mistake. It must read as a typo, not as a broken tool."""
import json

import pytest

from genesis_toolkit import cli
from tests.fixtures.make_fixture import build_fixture_rom


def test_missing_rom_reports_cleanly(tmp_path, capsys):
    assert cli.main(["header", str(tmp_path / "nope.md")]) == 1
    assert "no such file" in capsys.readouterr().err


def test_missing_map_points_at_the_working_directory(tmp_path, capsys):
    rom = tmp_path / "rom.md"
    rom.write_bytes(build_fixture_rom())
    assert cli.main(["map-list", str(rom), "maps/nowhere.json"]) == 1
    err = capsys.readouterr().err
    assert "no such map file" in err
    assert "full path" in err


def test_missing_mod_reports_cleanly(tmp_path, capsys):
    rom = tmp_path / "rom.md"
    rom.write_bytes(build_fixture_rom())
    assert cli.main(["patch", str(rom), str(tmp_path / "nope.json"),
                     str(tmp_path / "out.md")]) == 1
    assert "no such mod file" in capsys.readouterr().err


def test_directory_instead_of_file_reports_cleanly(tmp_path, capsys):
    assert cli.main(["header", str(tmp_path)]) == 1
    assert "is a directory" in capsys.readouterr().err


def test_malformed_mod_reports_cleanly(tmp_path, capsys):
    rom = tmp_path / "rom.md"
    rom.write_bytes(build_fixture_rom())
    mod = tmp_path / "mod.json"
    mod.write_text("{not json")
    assert cli.main(["patch", str(rom), str(mod), str(tmp_path / "out.md")]) == 1
    assert "invalid JSON" in capsys.readouterr().err


def test_happy_path_still_works(tmp_path, capsys):
    rom = tmp_path / "rom.md"
    rom.write_bytes(build_fixture_rom())
    mod = tmp_path / "mod.json"
    mod.write_text(json.dumps({"name": "t", "edits": [
        {"at": "0x500", "bytes": "4e71"}]}))
    out = tmp_path / "out.md"
    assert cli.main(["patch", str(rom), str(mod), str(out)]) == 0
    assert out.read_bytes()[0x500:0x502] == b"\x4e\x71"
