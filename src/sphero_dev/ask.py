"""``sphero-dev ask``: Claude writes an Edu-app program, the simulator checks it.

The conversation gives Claude two tools:

- ``simulate`` runs a draft in :class:`~sphero_dev.backends.SimBackend` and
  reports where the robot went, so Claude can check and fix its own work.
- ``propose_program`` hands the finished program to the user. It's
  simulated once more and rejected if it crashes or hangs.

Programs are in the Edu app's dialect, so they also paste into the app.
Running one on a robot is the CLI's job (``cli.py``), and only after the
user says so.
"""

from __future__ import annotations

import ast
import contextlib
import io
import multiprocessing
import queue
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

MODEL = "claude-sonnet-5-5"
MAX_TOOL_ROUNDS = 12
SIM_WALL_CLOCK_S = 20.0

# What the simulator assumes, matched to a real BOLT+ run (see AGENTS.md).
# tau 0.45: from rest at speed 50 it barely moves for ~0.5 s and is at speed by ~0.9 s.
SIM_SETTINGS = {"delay_overhead": 0.1, "turn_lag": 0.2, "command_latency": 0.1, "tau": 0.45,
                "min_moving_speed": 35}

RULES = """\
You write programs for a Sphero BOLT or BOLT+ robot in the Sphero Edu app's \
Python dialect. The user's computer runs them with sphero-dev, which provides \
the same built-in commands as the Edu app, so they also paste into the app \
unchanged.

# The dialect

- No imports at all (no math, random, time, asyncio). The commands below are \
globals. Do math by hand: `x ** 0.5`, 57.29578 degrees per radian, a \
hand-written atan2 if you need one.
- The entry point is `async def start_program():`. Top-level code only \
defines constants and helper functions.
- `await` the timed calls: delay, roll, spin, fade, strobe, raw_motor, speak, \
scroll_matrix_text. Everything else returns at once and is not awaited.
- Every loop must contain an `await` (usually `await delay(...)`), or the \
program freezes.
- Colors are dicts: {'r': 255, 'g': 0, 'b': 0}.
- No connect, scan, aim or cleanup code. The host connects, and stops the \
robot when the program ends or its time runs out.
- Start the file with a comment block: what it does, "Runtime: Sphero Edu app \
(or sphero-dev run)", "Written by sphero-dev ask; simulated, not tested on \
hardware".

# Driving facts

- Heading is degrees: 0 is the direction the robot was aimed, 90 right, 180 \
back, 270 left. Location is in cm from the start: +y forward, +x right.
- Speed is 0-255, not a physical unit. On a BOLT+ on a hard floor speed 90 \
is about 63 cm/s (0.7 cm/s per unit, roughly).
- Don't time distances or turns with delay(): each loop in the app takes \
longer than the delay asked for, so timed paths come out too big. Steer \
from sensors instead: get_location(), get_distance(), get_heading(), \
get_velocity().
- The BOLT+'s heading lags the command (about 0.2 s), and it turns at \
least 82 deg/s at 60 cm/s but tight high-speed turns slip. For tight \
paths adapt speed to tracking error rather than picking a fast fixed speed. \
A path-follower that relies on hitting the commanded heading exactly sits \
off the path; an integral correction fixes that.
- Each command sent to the robot (set_speed, set_heading, stop_roll, \
lights, matrix) takes about 0.1 s and the program waits for it; reading \
a sensor is instant. A set_heading or set_speed that changes nothing is \
free. In loops, only change what needs changing.
- `roll(heading, speed, duration)` stops the robot when its time is up. \
To drive continuously while steering, use set_heading() and set_speed() \
with `await delay(...)` in the loop, and stop_roll() at the end. Don't \
call roll() in a loop of short steps: the robot stops and restarts every \
step, and from a stop it takes about 0.5-1 s to get going again (longer \
if it first has to turn on the spot).
- Sensor readings update about 6 times a second.
- Below about speed 35 a BOLT+ barely moves on a hard floor (a few cm/s). \
Don't creep slower than 40 near a target; stop early and let it coast.
- Rooms are small. Unless asked otherwise, keep the path within about \
1.5 m of the start.
- Location comes from the wheels. On a soft surface (a bed, thick carpet) \
or against an obstacle the wheels spin inside the shell and the robot \
barely moves, so a loop waiting to reach a point may never finish. Give \
every "drive until" loop a time limit (count loop passes) and move on when \
it runs out.

# How to work

1. Write the program and check it with `simulate`. Read the numbers: does \
the path have the size, shape and speed the user asked for? Fix and \
re-simulate until it does. The simulator is rough (no slipping, no \
collisions, lights only logged) but catches crashes, hangs and wrong \
geometry.
2. Call `propose_program` with the final program. Never put the program in \
your text reply; it only reaches the user through `propose_program`.
3. If the request leaves details open (size, speed, colors), choose sensible \
defaults and say what you chose in the summary instead of asking. Ask a \
question in plain text only if you really can't proceed.
4. The user may run the program on the real robot and tell you what \
happened. Trust their report over the simulator, and adjust.
"""

TOOLS = [
    {
        "name": "simulate",
        "description": (
            "Run an Edu-app program in sphero-dev's simulator and report errors, printed "
            "output, the commands it sent and the robot's path (cm, once a second). Use it "
            "to check a draft before proposing it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The complete program."},
                "seconds": {"type": "integer",
                            "description": "How long to simulate, 1-120 seconds."},
            },
            "required": ["code", "seconds"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "propose_program",
        "description": (
            "Hand the finished program to the user. It is simulated again; if it crashes "
            "or hangs you get the error back instead. Otherwise the user sees the code, "
            "your summary and the simulated path, and decides whether to run it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string",
                          "description": "Short program name, e.g. 'Figure eight'."},
                "summary": {"type": "string",
                            "description": "Two or three sentences: what it does, and any "
                                           "defaults you chose."},
                "code": {"type": "string", "description": "The complete program."},
            },
            "required": ["title", "summary", "code"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _read_text(package_file: str, repo_fallback: str) -> str:
    """Read a file packaged with sphero_dev, or from the repo in an editable install."""
    res = resources.files("sphero_dev").joinpath(package_file)
    if res.is_file():
        return res.read_text(encoding="utf-8")
    return (Path(__file__).resolve().parents[2] / repo_fallback).read_text(encoding="utf-8")


def system_prompt() -> str:
    stubs = _read_text("edu_builtins.pyi", "src/sphero_dev/edu_builtins.pyi")
    reference = _read_text("api-reference.md", "docs/api-reference.md")
    example = _read_text("example_square.py", "examples/edu_app/square.py")
    return (f"{RULES}\n# Built-in commands (type stubs)\n\n```python\n{stubs}```\n\n"
            f"# Command reference\n\n{reference}\n\n"
            "# A program that worked on a real BOLT+\n\n"
            "Use its drive-to-a-point pattern when a path has corners or targets.\n\n"
            f"```python\n{example}```\n")


# --- simulator tool ---------------------------------------------------------

@dataclass
class SimResult:
    ok: bool
    report: str
    distance: float = 0.0
    # (t s, x cm, y cm, heading deg, ground speed cm/s), one per simulator step.
    trace: list[tuple[float, float, float, int, float]] = field(default_factory=list)


def _sim_worker(code: str, seconds: float, max_speed: int, out: Any) -> None:
    import asyncio

    from .backends import SimBackend
    from .edu import run_source

    log: list[str] = []
    sim = SimBackend(max_speed=max_speed, log=log.append, **SIM_SETTINGS)
    printed = io.StringIO()
    error = None
    try:
        with contextlib.redirect_stdout(printed):
            asyncio.run(run_source(code, sim, seconds))
    except BaseException as e:  # report anything the program raises
        lines = traceback.format_exception(type(e), e, e.__traceback__)
        # Keep the frames in the user's program, plus the error itself.
        keep = [ln for ln in lines if "<program>" in ln] + lines[-1:]
        error = "".join(keep).strip()
    out.put({
        "error": error,
        "t": sim.t,
        "distance": sim.distance,
        "final": (sim.x, sim.y),
        "trace": sim.trace,
        "log": log,
        "printed": printed.getvalue(),
    })


def _summarize(r: dict[str, Any], seconds: float) -> str:
    trace = r["trace"]
    lines = []
    if r["error"]:
        lines.append(f"ERROR at t={r['t']:.1f} s:\n{r['error']}")
    elif r["t"] < seconds - 0.05:
        lines.append(f"The program finished by itself after {r['t']:.1f} s.")
    else:
        lines.append(f"Ran the full {seconds:g} s without errors.")
    if trace:
        xs = [p[1] for p in trace]
        ys = [p[2] for p in trace]
        top = max(p[4] for p in trace)
        lines.append(
            f"Travelled {r['distance']:.0f} cm. Ended at ({r['final'][0]:.0f}, "
            f"{r['final'][1]:.0f}) cm. Path spans x {min(xs):.0f}..{max(xs):.0f}, "
            f"y {min(ys):.0f}..{max(ys):.0f} cm. Top ground speed {top:.0f} cm/s.")
        lines.append("Path, once a second (t s: x, y cm, heading deg, speed cm/s):")
        next_t = 0.0
        for t, x, y, h, v in trace:
            if t >= next_t:
                lines.append(f"  {t:5.1f}: {x:6.0f}, {y:6.0f}, {h:3d}, {v:4.0f}")
                next_t += 1.0
    else:
        lines.append("The robot never moved.")
    if r["log"]:
        counts: dict[str, int] = {}
        for entry in r["log"]:
            name = re.sub(r"^\[[ \d.]+s\] ", "", entry).split("(")[0]
            counts[name] = counts.get(name, 0) + 1
        lines.append("Logged commands: " + ", ".join(
            f"{name} x{n}" for name, n in sorted(counts.items())))
        lines.append("First few: " + "; ".join(r["log"][:8]))
    if r["printed"]:
        lines.append("Printed:\n" + r["printed"][:2000])
    return "\n".join(lines)


def check_dialect(code: str) -> str | None:
    """Return why ``code`` won't work in the Edu app, or None if it looks fine."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError on line {e.lineno}: {e.msg}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return (f"Line {node.lineno} imports a module. The Edu app has no imports; "
                    "use the built-in commands and do math by hand.")
    if not any(isinstance(n, ast.AsyncFunctionDef) and n.name == "start_program"
               for n in tree.body):
        return "No `async def start_program():` at the top level."
    return None


HUNG = ("ERROR: the simulation hung. A loop probably has no `await`; "
        "every loop needs one (e.g. `await delay(0.05)`).")

# iOS apps can't start processes, so there the simulation runs in a thread with a
# watchdog instead (see _simulate_in_thread).
SIM_IN_THREAD = sys.platform == "ios"


class _SimTimeout(BaseException):
    """Raised inside the program by the watchdog; BaseException so `except Exception`
    in the program can't swallow it."""


def _simulate_in_thread(code: str, seconds: float, max_speed: int) -> SimResult:
    """Like the child process, but stop a runaway program by tracing its lines.

    Only the program's own frames (``<program>``) are traced, so the simulator
    itself runs at full speed.
    """
    deadline = time.monotonic() + SIM_WALL_CLOCK_S
    results: list[dict[str, Any]] = []

    def line(frame: Any, event: str, arg: Any) -> Any:
        if time.monotonic() > deadline:
            raise _SimTimeout
        return line

    def call(frame: Any, event: str, arg: Any) -> Any:
        return line if frame.f_code.co_filename == "<program>" else None

    def worker() -> None:
        sys.settrace(call)
        try:
            _sim_worker(code, seconds, max_speed, SimpleNamespace(put=results.append))
        finally:
            sys.settrace(None)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(SIM_WALL_CLOCK_S + 5)
    if not results or (time.monotonic() > deadline and "_SimTimeout" in str(results[0]["error"])):
        return SimResult(False, HUNG)
    result = results[0]
    return SimResult(result["error"] is None, _summarize(result, seconds), result["distance"],
                     result["trace"])


def simulate(code: str, seconds: float, max_speed: int = 255) -> SimResult:
    """Run ``code`` in a child process so a program that never awaits can't hang us."""
    problem = check_dialect(code)
    if problem:
        return SimResult(False, f"ERROR: {problem}")
    seconds = max(1.0, min(120.0, float(seconds)))
    if SIM_IN_THREAD:
        return _simulate_in_thread(code, seconds, max_speed)
    ctx = multiprocessing.get_context("spawn")
    out = ctx.Queue()
    proc = ctx.Process(target=_sim_worker, args=(code, seconds, max_speed, out), daemon=True)
    proc.start()
    try:
        result = out.get(timeout=SIM_WALL_CLOCK_S)
    except queue.Empty:
        proc.kill()
        proc.join()
        return SimResult(False, HUNG)
    proc.join()
    return SimResult(result["error"] is None, _summarize(result, seconds), result["distance"],
                     result["trace"])


# --- conversation -----------------------------------------------------------

class AskError(Exception):
    """Claude couldn't produce a program (refusal, too many rounds, ...)."""


@dataclass
class Proposal:
    title: str
    summary: str
    code: str
    sim_report: str
    # The simulated path: (t s, x cm, y cm, heading deg, speed cm/s).
    sim_trace: list[tuple[float, float, float, int, float]] = field(default_factory=list)


@dataclass
class Reply:
    """Claude's turn: a program, or a plain-text message (usually a question)."""

    proposal: Proposal | None
    text: str


@dataclass
class Conversation:
    """One request and its follow-ups. ``client`` is an ``anthropic.Anthropic()``."""

    client: Any
    max_speed: int = 255
    seconds: float = 30.0
    space_cm: float | None = None
    effort: str = "medium"
    model: str = MODEL
    status: Callable[[str], None] = print
    messages: list[dict[str, Any]] = field(default_factory=list)
    _pending: list[dict[str, Any]] = field(default_factory=list)
    _system: str = field(default_factory=system_prompt)

    def send(self, text: str) -> Reply:
        if not self.messages:
            space = (f" There is about {self.space_cm:g} cm of clear floor around the start; "
                     "keep the whole path inside it." if self.space_cm else "")
            text = (f"{text}\n\n(Limits for this robot: speed is capped at {self.max_speed}, "
                    f"and each run is stopped after {self.seconds:g} seconds.{space})")
        # Tool results still owed from the last turn go in the same user message.
        self.messages.append({"role": "user",
                              "content": [*self._pending, {"type": "text", "text": text}]})
        self._pending = []
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._create()
            if response.stop_reason == "refusal":
                self.messages.pop()
                raise AskError("Claude declined this request.")
            if response.stop_reason == "max_tokens":
                raise AskError("Claude's reply was cut off (max_tokens).")
            self.messages.append({"role": "assistant", "content": response.content})
            said = "\n".join(b.text for b in response.content if b.type == "text").strip()
            calls = [b for b in response.content if b.type == "tool_use"]
            if not calls:
                return Reply(None, said)
            if said:
                self.status(said)
            results, proposal = [], None
            for call in calls:
                content, is_error, prop = self._run_tool(call.name, call.input)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": content, "is_error": is_error})
                proposal = prop or proposal
            if proposal:
                # Owed to Claude; sent with the user's next message, if any.
                self._pending = results
                return Reply(proposal, said)
            self.messages.append({"role": "user", "content": results})
        raise AskError(f"No program after {MAX_TOOL_ROUNDS} rounds of tool calls.")

    def _create(self) -> Any:
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            cache_control={"type": "ephemeral"},
            system=self._system,
            tools=TOOLS,
            messages=self.messages,
        )

    def _run_tool(self, name: str, args: dict[str, Any]) -> tuple[str, bool, Proposal | None]:
        needed = {"simulate": ["code"], "propose_program": ["title", "summary", "code"]}
        missing = [k for k in needed.get(name, []) if not args.get(k)]
        if missing:
            return f"{name} needs {', '.join(missing)}.", True, None
        if name == "simulate":
            self.status(f"  simulating {args.get('seconds', self.seconds)} s...")
            result = simulate(args["code"], args.get("seconds", self.seconds), self.max_speed)
            return result.report, not result.ok, None
        if name == "propose_program":
            self.status("  checking the final program...")
            result = simulate(args["code"], self.seconds, self.max_speed)
            if not result.ok:
                return f"Not shown to the user; it failed in the simulator:\n{result.report}", \
                    True, None
            if result.distance < 1 and re.search(r"\b(roll|set_speed|raw_motor)\(", args["code"]):
                return ("Not shown to the user: it sends drive commands but the robot never "
                        f"moved in the simulator. Fix that first.\n{result.report}"), True, None
            proposal = Proposal(args["title"], args["summary"], args["code"], result.report,
                                result.trace)
            return "Shown to the user, who decides whether to run it.", False, proposal
        return f"Unknown tool {name!r}.", True, None
