"""Command line: ``sphero-dev run program.py [--robot NAME | --sim]``."""

from __future__ import annotations

import argparse
import asyncio
import csv
import shutil
import sys
from importlib import resources
from pathlib import Path

from .backends import RobotBackend, SimBackend
from .edu import run_program


def _run_sim(args: argparse.Namespace) -> int:
    sim = SimBackend(log=print if args.verbose else None)
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


def _run_robot(args: argparse.Namespace) -> int:
    from spherov2 import scanner
    from spherov2.sphero_edu import SpheroEduAPI

    print(f"Scanning for {args.robot or 'a robot'}...")
    toy = scanner.find_toy(toy_name=args.robot)
    print(f"Connecting to {toy.name}. Aim it so the blue tail light faces you.")
    with SpheroEduAPI(toy) as api:
        try:
            asyncio.run(run_program(args.program, RobotBackend(api), args.seconds))
        except KeyboardInterrupt:
            print("\nStopping.")
            api.stop_roll()
    return 0


def _stubs(args: argparse.Namespace) -> int:
    dest = Path(args.directory) / "__builtins__.pyi"
    src = resources.files("sphero_dev").joinpath("edu_builtins.pyi")
    with resources.as_file(src) as p:
        shutil.copyfile(p, dest)
    print(f"Wrote {dest}. Pyright/Pylance will now know the Edu app's built-in commands "
          "for files in that folder.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sphero-dev")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a Sphero Edu app program on a robot or the simulator")
    run.add_argument("program", help="an Edu-app .py file with `async def start_program():`")
    where = run.add_mutually_exclusive_group()
    where.add_argument("--robot", metavar="NAME",
                       help="robot name, e.g. SB-1234 (default: first found)")
    where.add_argument("--sim", action="store_true",
                       help="run in the simulator instead of on a robot")
    run.add_argument("--seconds", type=float, help="stop after this long (sim default: 30)")
    run.add_argument("--trace", metavar="CSV", help="sim only: write the path to a CSV file")
    run.add_argument("-v", "--verbose", action="store_true", help="sim only: log commands")

    stubs = sub.add_parser("stubs", help="write __builtins__.pyi so editors know the Edu commands")
    stubs.add_argument("directory", nargs="?", default=".")

    args = parser.parse_args(argv)
    if args.command == "stubs":
        return _stubs(args)
    return _run_sim(args) if args.sim else _run_robot(args)


if __name__ == "__main__":
    sys.exit(main())
