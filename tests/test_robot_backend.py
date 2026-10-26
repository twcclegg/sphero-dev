"""RobotBackend against a fake SpheroEduAPI (no Bluetooth)."""

import asyncio

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
