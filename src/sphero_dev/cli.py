"""Command line: ``sphero-dev run program.py [--robot NAME | --sim]``, ``sphero-dev ask``, ..."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import math
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Iterator

from . import lab
from .backends import RobotBackend, RobotHalted, SimBackend
from .edu import run_program, run_source


def _run_sim(args: argparse.Namespace) -> int:
    sim = SimBackend(log=print if args.verbose else None, delay_overhead=args.delay_overhead,
                     max_turn_rate=args.max_turn_rate, turn_lag=args.turn_lag,
                     command_latency=args.command_latency)
    seconds = args.seconds if args.seconds is not None else 30.0
    asyncio.run(run_program(args.program, sim, seconds))
    xs = [p[1] for p in sim.trace] or [0.0]
    ys = [p[2] for p in sim.trace] or [0.0]
    print(f"Simulated {sim.t:.1f} s: travelled {sim.distance:.0f} cm, "
          f"ended at ({sim.x:.0f}, {sim.y:.0f}) cm, "
          f"path spans {max(xs) - min(xs):.0f} x {max(ys) - min(ys):.0f} cm")
    if args.trace:
        with open(args.trace, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "x_cm", "y_cm", "heading", "speed_cm_s"])
            w.writerows(sim.trace)
        print(f"Wrote {len(sim.trace)} samples to {args.trace}")
    return 0


class _Unhealthy(Exception):
    pass


def _check_stream(api: Any, toy: Any) -> None:
    """Wait for sensor data, then make sure it's arriving intact.

    Sensors read None until the first streamed sample arrives, which Edu-app
    programs don't expect. And after some failed connection attempts
    (``br-connection-canceled``) the stream arrives garbled, so the robot
    would drive blind; better to reconnect before the program starts.
    """
    if hasattr(toy, "sensor_control"):
        # spherov2 streams every 250 ms; the Edu app about every 150 ms.
        toy.sensor_control.set_interval(150)
    deadline = time.monotonic() + 3
    while api.get_location() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(0.5)
    if api.get_location() is None:
        raise _Unhealthy("no sensor data arrived")
    if _decode_errors(toy):
        raise _Unhealthy("its data arrived garbled")


@contextlib.contextmanager
def _connect(find: Callable[[], Any], api_cls: Any,
             attempts: int = 3) -> Iterator[tuple[Any, Any]]:
    """Connect to ``find()``'s toy as ``api_cls(toy)``, retrying; yields ``(api, toy)``.

    On Linux the first connection after a scan often fails ("Device with
    address ... was not found", "Operation already in progress", or a bare
    TimeoutError from spherov2's 5 s connect), and the next attempt usually
    works. Each attempt scans again for a fresh toy, and the connection is
    only used once :func:`_check_stream` passes.
    """
    for attempt in range(1, attempts + 1):
        toy = find()
        api = api_cls(toy)
        entered = False
        try:
            api.__enter__()
            entered = True
            _check_stream(api, toy)
            break
        except Exception as e:
            try:  # leave the toy disconnected so the next attempt starts fresh
                if entered:
                    api.__exit__(None, None, None)
                else:
                    toy.__exit__(None, None, None)
            except Exception:
                pass
            if attempt == attempts:
                raise
            print(f"Couldn't connect ({type(e).__name__}{': ' + str(e) if str(e) else ''}); "
                  "trying again...")
            time.sleep(3)
    try:
        yield api, toy
    finally:
        api.__exit__(None, None, None)


def _decode_errors(toy: Any) -> int:
    from .toys import decode_errors

    return decode_errors(toy)


class _PathRecorder:
    """Samples the robot's sensors on a thread while a program runs.

    It's also the watchdog: if the robot's data turns to garbage or stops
    arriving, the program can't know where the robot is, so it halts the
    backend (stops the robot) rather than let it drive blind.
    """

    def __init__(self, api: Any, toy: Any, backend: RobotBackend, every: float = 0.25,
                 stop: threading.Event | None = None):
        self.api, self.toy, self.backend, self.every = api, toy, backend, every
        self.stop_requested = stop
        self._errors0 = _decode_errors(toy)
        self._last_data = time.monotonic()
        if hasattr(toy, "sensor_control"):
            toy.sensor_control.add_sensor_data_listener(self._on_data)
        self.samples: list[tuple[float, float, float, int, float, int]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _PathRecorder:
        self._t0 = time.monotonic()
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        self._thread.join()

    def _on_data(self, _data: Any) -> None:
        self._last_data = time.monotonic()

    def _check(self) -> None:
        if self.stop_requested is not None and self.stop_requested.is_set():
            self.backend.halt("stop was pressed")
        elif _decode_errors(self.toy) - self._errors0 >= 3:
            self.backend.halt("the robot's Bluetooth data was garbled, so the program couldn't "
                              "tell where the robot was")
        elif time.monotonic() - self._last_data > 1.0:
            self.backend.halt("sensor data stopped arriving")

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            self._check()
            loc = self.api.get_location() or {"x": 0.0, "y": 0.0}
            vel = self.api.get_velocity() or {"x": 0.0, "y": 0.0}
            self.samples.append((time.monotonic() - self._t0, loc["x"], loc["y"],
                                 int(self.api.get_heading() or 0),
                                 math.hypot(vel["x"], vel["y"]), int(self.api.get_speed() or 0)))

    def stuck(self) -> list[tuple[float, float]]:
        """Stretches of 1.5 s or more told to move (speed > 20) but under 5 cm/s.

        Shorter ones are normal: turning on the spot from a stop takes ~0.8 s.
        """
        spans, begin = [], None
        for t, _x, _y, _h, v, cmd in self.samples:
            if abs(cmd) > 20 and v < 5:
                begin = t if begin is None else begin
            else:
                if begin is not None and t - begin >= 1.5:
                    spans.append((begin, t))
                begin = None
        if begin is not None and self.samples and self.samples[-1][0] - begin >= 1.5:
            spans.append((begin, self.samples[-1][0]))
        return spans

    def path(self) -> str:
        lines, next_t = [], 0.0
        for t, x, y, h, v, cmd in self.samples:
            if t >= next_t:
                lines.append(f"  {t:5.1f}: {x:6.0f}, {y:6.0f}, {h:3d}, {v:4.0f}  (speed {cmd})")
                next_t += 1.0
        return "\n".join(lines)


@dataclass
class RobotRun:
    summary: str  # one or two sentences for the user
    details: str  # the path, once a second, for Claude
    # Every sensor sample: (t s, x cm, y cm, heading deg, speed cm/s, commanded speed).
    samples: list[tuple[float, float, float, int, float, int]] = field(default_factory=list)


def run_on_robot(source: str, robot: str | None, seconds: float | None,
                 max_speed: int = 255, filename: str = "<program>",
                 stop: threading.Event | None = None, adapter: Any = None) -> RobotRun:
    """Find a robot, connect, and run an Edu-app program on it.

    Ctrl-C stops it, and so does setting ``stop`` (from another thread).
    ``adapter`` is a spherov2 Bluetooth adapter class (default: bleak's; the
    iOS app passes :class:`~sphero_dev.ios_adapter.IOSAdapter`).
    """
    from spherov2 import scanner
    from spherov2.sphero_edu import SpheroEduAPI

    from .toys import BOLTPlus

    def find() -> Any:
        print(f"Scanning for {robot or 'a robot'}...")
        try:
            toy = scanner.find_toy(toy_name=robot, toy_types=[*scanner.all_toys(), BOLTPlus],
                                   timeout=10, adapter=adapter)
        except scanner.ToyNotFoundError:
            # A BOLT+ sleeps about a minute after it was last connected.
            raise RuntimeError(f"No robot{' named ' + robot if robot else ''} found. Wake it "
                               "(shake or tap it) and make sure the Edu app isn't "
                               "connected to it.") from None
        print(f"Connecting to {toy.name}. Aim it so the blue tail light faces you.")
        return toy

    with _connect(find, SpheroEduAPI) as (api, toy):
        print("Running. Ctrl-C stops it.")
        start = time.monotonic()
        how = "finished by itself"
        backend = RobotBackend(api, max_speed)
        with _PathRecorder(api, toy, backend, stop=stop) as rec:
            try:
                asyncio.run(run_source(source, backend, seconds, filename))
            except KeyboardInterrupt:
                print("\nStopping.")
                api.stop_roll()
                how = "stopped with Ctrl-C"
            except RobotHalted as e:
                how = f"stopped for safety: {e}"
        elapsed = time.monotonic() - start
        if seconds is not None and elapsed >= seconds - 0.5:
            how = f"stopped at the {seconds:g} s limit"
        distance = api.get_distance() or 0.0
        loc = api.get_location() or {"x": 0.0, "y": 0.0}
    moved = (f"The robot's sensors say it travelled {distance:.0f} cm and ended "
             f"{loc['x']:.0f} cm right, {loc['y']:.0f} cm forward of where it started."
             if distance >= 2 else "The robot didn't move.")
    summary = f"Ran for {elapsed:.1f} s ({how}). {moved}"
    stuck = rec.stuck()
    if stuck:
        summary += (" It looked stuck (told to move, barely moving: blocked, or slipping) at "
                    + ", ".join(f"{a:.0f}-{b:.0f} s" for a, b in stuck) + ".")
    details = ("Measured path, once a second (t s: x, y cm, heading deg, speed cm/s, "
               "commanded speed):\n" + rec.path())
    return RobotRun(summary, details, rec.samples)


def _run_robot(args: argparse.Namespace) -> int:
    path = Path(args.program)
    source = lab.read(path).code if path.suffix == ".lab" else path.read_text(encoding="utf-8")
    run = run_on_robot(source, args.robot, args.seconds, args.max_speed, str(path))
    print(run.summary)
    print(run.details)
    return 0


def _stubs(args: argparse.Namespace) -> int:
    dest = Path(args.directory) / "__builtins__.pyi"
    src = resources.files("sphero_dev").joinpath("edu_builtins.pyi")
    with resources.as_file(src) as p:
        shutil.copyfile(p, dest)
    print(f"Wrote {dest}. Pyright/Pylance will now know the Edu app's built-in commands "
          "for files in that folder.")
    return 0


def _export(args: argparse.Namespace) -> int:
    src = Path(args.program)
    dest = Path(args.output) if args.output else src.with_suffix(".lab")
    lab.write(lab.LabProgram(name=args.name or src.stem, code=src.read_text(encoding="utf-8")),
              dest)
    print(f"Wrote {dest}. Open it with the Sphero Edu app to add it to your programs.")
    return 0


def _import(args: argparse.Namespace) -> int:
    src = Path(args.lab_file)
    program = lab.read(src)
    dest = Path(args.output) if args.output else src.with_suffix(".py")
    dest.write_text(program.code + "\n", encoding="utf-8")
    print(f"Wrote {dest} (program {program.name!r}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sphero-dev")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a Sphero Edu app program on a robot or the simulator")
    run.add_argument("program",
                     help="an Edu-app .py or .lab file with `async def start_program():`")
    where = run.add_mutually_exclusive_group()
    where.add_argument("--robot", metavar="NAME",
                       help="robot name, e.g. SB-1234 (default: first found)")
    where.add_argument("--sim", action="store_true",
                       help="run in the simulator instead of on a robot")
    run.add_argument("--seconds", type=float, help="stop after this long (sim default: 30)")
    run.add_argument("--max-speed", type=int, default=255, metavar="N",
                     help="robot only: cap every speed the program asks for (0-255)")
    run.add_argument("--trace", metavar="CSV", help="sim only: write the path to a CSV file")
    run.add_argument("--delay-overhead", type=float, default=0.0, metavar="S",
                     help="sim only: extra seconds per delay, like a slow app loop (try 0.1)")
    run.add_argument("--max-turn-rate", type=float, metavar="DEG_S",
                     help="sim only: cap how fast the robot turns, in degrees/s (try 90)")
    run.add_argument("--turn-lag", type=float, default=0.0, metavar="S",
                     help="sim only: heading response time constant (a BOLT+ fits 0.2)")
    run.add_argument("--command-latency", type=float, default=0.0, metavar="S",
                     help="sim only: time each robot command takes (a BOLT+ over BLE: 0.1)")
    run.add_argument("-v", "--verbose", action="store_true", help="sim only: log commands")

    stubs = sub.add_parser("stubs", help="write __builtins__.pyi so editors know the Edu commands")
    stubs.add_argument("directory", nargs="?", default=".")

    export = sub.add_parser("export", help="convert an Edu-app .py program to a .lab file")
    export.add_argument("program")
    export.add_argument("-o", "--output", help="output path (default: same name, .lab)")
    export.add_argument("--name", help="program name shown in the app (default: file name)")

    imp = sub.add_parser("import", help="extract the Python code from a .lab file")
    imp.add_argument("lab_file")
    imp.add_argument("-o", "--output", help="output path (default: same name, .py)")

    ask = sub.add_parser("ask", help="describe a program; Claude writes it, the simulator "
                                     "checks it, you choose whether to run it")
    ask.add_argument("request", nargs="*",
                     help='what to do, e.g. "drive a square, 50 cm a side" (asked if omitted)')
    ask.add_argument("--robot", metavar="NAME", help="robot name, e.g. BP-5FBB "
                                                     "(default: first found)")
    ask.add_argument("--seconds", type=float, default=30.0,
                     help="stop each run after this long (default: 30)")
    ask.add_argument("--max-speed", type=int, default=150, metavar="N",
                     help="cap on speed, 0-255, for the robot and the simulator (default: 150)")
    ask.add_argument("--space", type=float, metavar="CM",
                     help="clear floor around the start, in cm; Claude keeps the path inside "
                          "it (default: not stated, Claude assumes about 1.5 m)")
    ask.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh"],
                     help="how hard Claude thinks (default: medium)")
    ask.add_argument("--model", default="claude-sonnet-5-5",
                     help="Claude model (default: claude-sonnet-5-5; claude-haiku-5-5 is "
                          "faster)")
    ask.add_argument("--via", default="auto", choices=["auto", "claude-code", "api"],
                     help="claude-code: your Claude subscription, through the `claude` CLI; "
                          "api: ANTHROPIC_API_KEY; auto: claude-code if `claude` is "
                          "installed (default)")
    ask.add_argument("-o", "--out-dir", default=".", help="where [s]ave writes files")

    args = parser.parse_args(argv)
    if args.command == "ask":
        from .ask_cli import ask_main

        return ask_main(args)
    if args.command == "stubs":
        return _stubs(args)
    if args.command == "export":
        return _export(args)
    if args.command == "import":
        return _import(args)
    return _run_sim(args) if args.sim else _run_robot(args)


if __name__ == "__main__":
    sys.exit(main())
