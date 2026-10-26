import asyncio
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
def test_circles_example_is_about_one_meter(overhead, clockwise, max_turn_rate):
    # On a real BOLT+ an earlier timing-based version drew much bigger
    # circles (slow app loop), and a fixed-speed version drew wandering
    # 1.5-2 m loops (robot can't turn fast enough). Check the size holds with
    # a slow loop and a turn-rate limit, and that it doesn't slow down more
    # than the turn limit forces it to.
    source = (ROOT / "examples" / "edu_app" / "circles.py").read_text()
    if not clockwise:
        source = source.replace("CLOCKWISE = True", "CLOCKWISE = False")
    sim = SimBackend(delay_overhead=overhead, max_turn_rate=max_turn_rate)
    g = load_program(source, sim)
    asyncio.run(sim.run_for(g["start_program"](), 40.0))
    pts = [p for p in sim.trace if p[0] > 15.0]
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
