import asyncio
import math
from pathlib import Path

import pytest

from sphero_dev import SimBackend, load_program, run_program

ROOT = Path(__file__).resolve().parents[1]
EDU_EXAMPLES = sorted((ROOT / "examples" / "edu_app").glob("*.py"))


@pytest.fixture
def run_sim(tmp_path):
    def run(source: str, seconds: float = 10.0) -> SimBackend:
        sim = SimBackend()
        path = tmp_path / "program.py"
        path.write_text(source)
        asyncio.run(run_program(path, sim, seconds))
        return sim

    return run


@pytest.mark.parametrize("path", EDU_EXAMPLES, ids=lambda p: p.name)
def test_edu_examples_run_in_sim(path):
    sim = SimBackend()
    asyncio.run(run_program(path, sim, 15.0))
    assert sim.t == pytest.approx(15.0, abs=0.05)


@pytest.mark.parametrize("clockwise", [True, False])
@pytest.mark.parametrize("overhead", [0.0, 0.1, 0.25])
@pytest.mark.parametrize("max_turn_rate", [None, 120, 60])
@pytest.mark.parametrize("turn_lag", [0.0, 0.2])
def test_circles_example_is_about_one_meter(overhead, clockwise, max_turn_rate, turn_lag):
    # Each earlier version failed on a real BOLT+ in a way the simulator now
    # models: a slow app loop (overhead), a turn-rate limit, and a steady
    # heading lag (0.2 s reproduces the real run of version 3). Check the
    # size holds and it doesn't slow down more than the turn limit forces.
    source = (ROOT / "examples" / "edu_app" / "circles.py").read_text()
    if not clockwise:
        source = source.replace("CLOCKWISE = True", "CLOCKWISE = False")
    sim = SimBackend(delay_overhead=overhead, max_turn_rate=max_turn_rate, turn_lag=turn_lag)
    g = load_program(source, sim)
    asyncio.run(sim.run_for(g["start_program"](), 50.0))
    pts = [p for p in sim.trace if p[0] > 20.0]
    width = max(p[1] for p in pts) - min(p[1] for p in pts)
    height = max(p[2] for p in pts) - min(p[2] for p in pts)
    assert width == pytest.approx(105, abs=8)
    assert height == pytest.approx(105, abs=8)
    center_x = 50 if clockwise else -50
    assert (max(p[1] for p in pts) + min(p[1] for p in pts)) / 2 == pytest.approx(center_x, abs=6)

    mean_speed = sum(p[4] for p in pts) / len(pts)
    possible = 0.7 * 170 if max_turn_rate is None else min(0.7 * 170, max_turn_rate * 0.01745 * 50)
    assert mean_speed > 0.7 * possible


def test_roll_moves_forward_then_stops(run_sim):
    sim = run_sim("async def start_program():\n    await roll(0, 100, 2)\n")
    assert sim.speed == 0
    assert sim.y > 100  # 100 * 0.7 cm/s for ~2 s, minus spin-up
    assert abs(sim.x) < 1


def test_roll_negative_speed_drives_backward(run_sim):
    sim = run_sim("async def start_program():\n    await roll(0, -100, 1)\n")
    assert sim.y < -30


def test_spin_ends_at_target_heading(run_sim):
    sim = run_sim("async def start_program():\n    set_heading(10)\n    await spin(90, 1)\n")
    assert sim.heading == 100


def test_time_limit_stops_infinite_loop(run_sim):
    sim = run_sim(
        "async def start_program():\n"
        "    set_speed(50)\n"
        "    while True:\n"
        "        await delay(0.1)\n",
        seconds=3.0,
    )
    assert sim.t == pytest.approx(3.0, abs=0.05)
    assert sim.speed == 0


def test_colors_accept_edu_dicts(run_sim):
    run_sim(
        "async def start_program():\n"
        "    set_main_led({'r': 255, 'g': 0, 'b': 0})\n"
        "    assert get_main_led() == {'r': 255, 'g': 0, 'b': 0}\n"
        "    await fade({'r': 0, 'g': 0, 'b': 0}, {'r': 0, 'g': 0, 'b': 255}, 0.5)\n"
        "    set_matrix_pixel(1, 2, {'r': 1, 'g': 2, 'b': 3})\n"
    )


def test_exit_program_ends_early(run_sim):
    sim = run_sim("async def start_program():\n    await delay(1)\n    exit_program()\n"
                  "    await delay(100)\n")
    assert sim.t == pytest.approx(1.0, abs=0.05)


def test_missing_start_program_is_an_error():
    with pytest.raises(ValueError, match="start_program"):
        load_program("x = 1\n", SimBackend())


def test_sim_reproduces_real_bolt_plus_run_of_circles_v3():
    # Version 3 of circles.py (no integral term) on a BOLT+ in the Edu app:
    # radius ~54 cm from (50, 0), about 36 cm/s, laps of ~9.5 s
    # (tests/data/circles_v3_bolt_plus_location.csv). With a 0.2 s heading
    # lag the simulator lands close to that, which is what makes it useful
    # for tuning; if this drifts, the model no longer matches the robot.
    import csv

    rows = list(csv.reader((ROOT / "tests" / "data" / "circles_v3_bolt_plus_location.csv").open()))
    real = [(float(t), float(x), float(y)) for t, x, y in rows[1:] if float(t) > 15]
    real_radius = sum(math.hypot(x - 50, y) for _, x, y in real) / len(real)
    assert real_radius == pytest.approx(54, abs=1)

    from sphero_dev import lab

    v3 = lab.read(ROOT / "tests" / "data" / "circles_v3.lab").code  # the file that ran
    sim = SimBackend(delay_overhead=0.1, turn_lag=0.2)
    g = load_program(v3, sim)
    asyncio.run(sim.run_for(g["start_program"](), 50.0))
    pts = [p for p in sim.trace if p[0] > 15.0]
    radius = sum(math.hypot(p[1] - 50, p[2]) for p in pts) / len(pts)
    speed = sum(p[4] for p in pts) / len(pts)
    assert radius == pytest.approx(real_radius, abs=2)
    assert speed == pytest.approx(36, abs=8)
