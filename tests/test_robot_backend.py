"""RobotBackend against a fake SpheroEduAPI (no Bluetooth)."""

import asyncio
from types import SimpleNamespace as NS

import pytest

from spherov2.types import Color

from sphero_dev import RobotBackend, run_program


class FakeApi:
    def __init__(self):
        self.calls = []
        self.heading = 0

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, args))

        return record

    def set_heading(self, heading):
        self.heading = heading
        self.calls.append(("set_heading", (heading,)))

    def get_heading(self):
        return self.heading


def test_program_drives_fake_robot(tmp_path):
    program = tmp_path / "p.py"
    program.write_text(
        "async def start_program():\n"
        "    set_main_led({'r': 1, 'g': 2, 'b': 3})\n"
        "    await roll(90, 120, 0.05)\n"
        "    set_matrix_pixel(0, 7, {'r': 9, 'g': 8, 'b': 7})\n"
    )
    api = FakeApi()
    asyncio.run(run_program(program, RobotBackend(api), seconds=5))
    assert ("set_main_led", (Color(1, 2, 3),)) in api.calls
    assert ("set_heading", (90,)) in api.calls
    assert ("set_speed", (120,)) in api.calls
    assert ("set_matrix_pixel", (0, 7, Color(9, 8, 7))) in api.calls
    assert api.calls[-1] == ("stop_roll", (None,))


def test_time_limit_on_robot(tmp_path):
    program = tmp_path / "p.py"
    program.write_text("async def start_program():\n    while True:\n        await delay(0.01)\n")
    api = FakeApi()
    asyncio.run(run_program(program, RobotBackend(api), seconds=0.2))
    assert api.calls[-1] == ("stop_roll", (None,))


def test_bolt_plus_names_match():
    from spherov2.scanner import all_toys

    from sphero_dev.toys import BOLTPlus

    tt = BOLTPlus.toy_type
    assert "BP-5FBB".startswith(tt.filter_prefix) and "BP-5FBB".startswith(tt.prefix)
    # spherov2's own types don't match BOLT+ names, which is why BOLTPlus exists.
    assert not any("BP-5FBB".startswith(t.toy_type.filter_prefix)
                   for t in all_toys() if t is not BOLTPlus)


def test_max_speed_caps_set_speed_and_roll():
    from sphero_dev.edu import run_source

    source = (
        "async def start_program():\n"
        "    set_speed(255)\n"
        "    await roll(0, -200, 0.01)\n"
    )
    api = FakeApi()
    asyncio.run(run_source(source, RobotBackend(api, max_speed=100), seconds=5))
    speeds = [args[0] for name, args in api.calls if name == "set_speed"]
    # 255 -> 100. The negative roll turns into heading + 180 at speed 200 -> 100;
    # its set_speed(100) is skipped because the robot is already at 100.
    assert speeds == [100]
    assert ("set_heading", (180,)) in api.calls


def test_unchanged_drive_commands_are_not_resent():
    backend = RobotBackend(FakeApi())
    for _ in range(5):
        backend.set_heading(90)
        backend.set_speed(60)
    backend.stop_roll(None)
    backend.set_speed(60)
    names = [name for name, _ in backend.api.calls]
    assert names == ["set_heading", "set_speed", "stop_roll", "set_speed"]


def test_halt_stops_the_robot_and_ends_the_program():
    from sphero_dev.backends import RobotHalted
    from sphero_dev.edu import run_source

    api = FakeApi()
    backend = RobotBackend(api)
    source = (
        "async def start_program():\n"
        "    set_speed(80)\n"
        "    await delay(0.01)\n"
        "    halt_now()\n"
        "    set_speed(90)\n"  # ignored
        "    await delay(0.01)\n"  # raises
        "    set_speed(100)\n"  # never reached
    )
    import sphero_dev.edu as edu

    real_load = edu.load_program

    def load(src, b, filename="<program>"):
        g = real_load(src, b, filename)
        g["halt_now"] = lambda: b.halt("test")
        return g

    edu.load_program, saved = load, edu.load_program
    try:
        with pytest.raises(RobotHalted):
            asyncio.run(run_source(source, backend, seconds=5))
    finally:
        edu.load_program = saved
    speeds = [args[0] for name, args in api.calls if name == "set_speed"]
    assert speeds == [80]
    assert ("stop_roll", ()) in api.calls


class _FakeToy:
    def __init__(self):
        self.listeners = []
        self.sensor_control = NS(add_sensor_data_listener=self.listeners.append)


@pytest.mark.parametrize("garbled", [False, True])
def test_watchdog_halts_when_data_stops_or_is_garbled(monkeypatch, garbled):
    import time

    from sphero_dev import cli

    errors = [0]
    monkeypatch.setattr(cli, "_decode_errors", lambda toy: errors[0])
    toy, api = _FakeToy(), FakeApi()
    backend = RobotBackend(api)
    rec = cli._PathRecorder(api, toy, backend)
    rec._check()
    assert backend.halted is None
    if garbled:
        errors[0] = 3
    else:
        rec._last_data = time.monotonic() - 2
    rec._check()
    assert backend.halted and ("garbled" in backend.halted) == garbled


def test_connect_retries_a_garbled_connection_with_a_fresh_toy(monkeypatch):
    from sphero_dev import cli

    toys = [NS(name="garbled", errors=5), NS(name="good", errors=0)]
    monkeypatch.setattr(cli, "_decode_errors", lambda toy: toy.errors)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)

    class Api:
        exited = []

        def __init__(self, toy):
            self.toy = toy

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            Api.exited.append(self.toy.name)

        def get_location(self):
            return {"x": 0.0, "y": 0.0}

    with cli._connect(lambda: toys.pop(0), Api) as (api, toy):
        assert toy.name == "good"
        assert Api.exited == ["garbled"]
    assert Api.exited == ["garbled", "good"]
