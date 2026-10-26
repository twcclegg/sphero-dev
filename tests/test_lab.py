import json
from pathlib import Path

import pytest

from sphero_dev import SimBackend, lab, run_program
from sphero_dev.cli import main

SAMPLE = Path(__file__).parent / "data" / "circles_bolt_plus.lab"


def test_reads_app_export():
    program = lab.read(SAMPLE)
    assert program.name == "Untitled Program (2)"
    assert program.robots == [{"id": 19, "name": "Sphero BOLT+"}]
    assert program.code.startswith("# Fast circles about 1 meter across.")
    assert "async def start_program():" in program.code


def test_round_trip_matches_app_bytes():
    # Re-serializing the app's own file reproduces it exactly.
    assert lab.dumps(lab.read(SAMPLE)) == SAMPLE.read_text(encoding="utf-8")


def test_export_import_cli(tmp_path):
    src = tmp_path / "prog.py"
    src.write_text("async def start_program():\n    await roll(0, 50, 1)\n")
    assert main(["export", str(src), "--name", "Roll test"]) == 0
    out = tmp_path / "prog.lab"
    d = json.loads(out.read_text())
    assert d["program_type"] == "text"
    assert d["data"] == "15;python&async def start_program():\n    await roll(0, 50, 1)"
    assert d["name"] == "Roll test"
    assert len(d["identifier"]) == 36 and d["identifier"] == d["identifier"].upper()

    back = tmp_path / "back.py"
    assert main(["import", str(out), "-o", str(back)]) == 0
    assert back.read_text() == src.read_text()


def test_rejects_block_programs():
    with pytest.raises(ValueError, match="text program"):
        lab.loads('{"program_type": "block", "data": ""}')


def test_run_lab_file_in_sim():
    import asyncio

    sim = SimBackend()
    asyncio.run(run_program(SAMPLE, sim, 10.0))
    assert sim.distance > 500
