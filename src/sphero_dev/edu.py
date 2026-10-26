"""Run Sphero Edu app programs outside the app.

An Edu-app Python program uses globals the app provides (``roll``,
``set_speed``, ``delay``, ...) and an ``async def start_program()`` entry
point. :func:`build_globals` recreates those globals on top of a backend,
and :func:`run_program` executes a program file with them.

A backend is any object with spherov2's ``SpheroEduAPI`` method names
(``set_speed``, ``set_heading``, ``get_velocity``, ...) plus ``sleep``.
See :mod:`sphero_dev.backends`.
"""

from __future__ import annotations

import asyncio
import enum
import inspect
from pathlib import Path
from typing import Any, Callable

# Calls the Edu app makes you ``await``. Everything else returns at once.
# This split is our best understanding of the app and isn't confirmed against
# Sphero's docs yet (see AGENTS.md, "Known unknowns").
AWAITED = frozenset({"delay", "roll", "spin", "fade", "strobe", "raw_motor", "speak",
                     "scroll_matrix_text"})

SPIN_STEP_S = 0.02


class EventType(enum.Enum):
    on_collision = "on_collision"
    on_freefall = "on_freefall"
    on_landing = "on_landing"
    on_gyro_max = "on_gyro_max"
    on_charging = "on_charging"
    on_not_charging = "on_not_charging"
    on_ir_message = "on_ir_message"
    on_color = "on_color"


class ProgramExit(Exception):
    """Raised by ``exit_program()`` to end a program early."""


def to_rgb(color: Any) -> tuple[int, int, int]:
    """Accept the Edu app's ``{'r', 'g', 'b'}`` dicts, tuples, or Color objects."""
    if isinstance(color, dict):
        return int(color.get("r", 0)), int(color.get("g", 0)), int(color.get("b", 0))
    if hasattr(color, "r"):
        return int(color.r or 0), int(color.g or 0), int(color.b or 0)
    r, g, b = color
    return int(r), int(g), int(b)


def build_globals(backend: Any) -> dict[str, Any]:
    """Return the global namespace an Edu-app program expects."""
    leds = {"main": (0, 0, 0)}

    def color_arg(color: Any) -> Any:
        return backend.color(*to_rgb(color))

    # --- instant calls -------------------------------------------------
    def set_speed(speed: int) -> None:
        backend.set_speed(int(speed))

    def set_heading(heading: int) -> None:
        backend.set_heading(int(heading))

    def stop_roll(heading: int | None = None) -> None:
        backend.stop_roll(None if heading is None else int(heading))

    def set_main_led(color: Any) -> None:
        leds["main"] = to_rgb(color)
        backend.set_main_led(color_arg(color))

    def set_back_led(color_or_brightness: Any) -> None:
        if isinstance(color_or_brightness, (int, float)):
            backend.set_back_led(int(color_or_brightness))
        else:
            backend.set_back_led(color_arg(color_or_brightness))

    def get_main_led() -> dict[str, int]:
        r, g, b = leds["main"]
        return {"r": r, "g": g, "b": b}

    def exit_program() -> None:
        raise ProgramExit

    # --- awaited calls -------------------------------------------------
    async def delay(seconds: float) -> None:
        await backend.sleep(float(seconds))

    async def roll(heading: int, speed: int, duration: float) -> None:
        if speed < 0:
            heading, speed = heading + 180, -speed
        backend.set_heading(int(heading) % 360)
        backend.set_speed(int(speed))
        await backend.sleep(float(duration))
        backend.stop_roll(None)

    async def spin(angle: float, duration: float) -> None:
        start = backend.get_heading()
        steps = max(1, round(duration / SPIN_STEP_S))
        for i in range(1, steps + 1):
            backend.set_heading(round(start + angle * i / steps) % 360)
            await backend.sleep(duration / steps)

    async def fade(from_color: Any, to_color: Any, duration: float) -> None:
        a, b = to_rgb(from_color), to_rgb(to_color)
        steps = max(1, round(duration / 0.05))
        for i in range(steps + 1):
            t = i / steps
            set_main_led(tuple(round(x + (y - x) * t) for x, y in zip(a, b)))
            await backend.sleep(duration / steps)

    async def strobe(color: Any, period: float, count: int) -> None:
        for _ in range(int(count)):
            set_main_led(color)
            await backend.sleep(period / 2)
            set_main_led((0, 0, 0))
            await backend.sleep(period / 2)

    async def raw_motor(left: int, right: int, duration: float) -> None:
        await backend.raw_motor(int(left), int(right), float(duration))

    async def speak(text: str, wait: bool = True) -> None:
        # The app speaks through the device; outside it we just print.
        print(f"[speak] {text}")

    async def scroll_matrix_text(text: str, color: Any, fps: int = 6, wait: bool = True) -> None:
        backend.scroll_matrix_text(str(text), color_arg(color), int(fps), False)
        if wait:
            # Roughly how long a scroll takes: one column per frame, 8 per char.
            await backend.sleep((len(text) * 8 + 8) / max(1, int(fps)))

    # --- events --------------------------------------------------------
    def register_event(event_type: EventType, handler: Callable[..., Any]) -> None:
        backend.register_event(event_type.value, handler)

    g: dict[str, Any] = {
        "__name__": "__sphero_edu__",
        "EventType": EventType,
        "set_speed": set_speed,
        "set_heading": set_heading,
        "stop_roll": stop_roll,
        "set_main_led": set_main_led,
        "set_back_led": set_back_led,
        "get_main_led": get_main_led,
        "exit_program": exit_program,
        "delay": delay,
        "roll": roll,
        "spin": spin,
        "fade": fade,
        "strobe": strobe,
        "raw_motor": raw_motor,
        "speak": speak,
        "scroll_matrix_text": scroll_matrix_text,
        "register_event": register_event,
    }

    # Everything else passes straight through to the backend when it has it.
    passthrough = [
        "set_stabilization", "reset_aim", "calibrate_compass", "set_compass_direction",
        "set_front_led", "set_matrix_pixel", "set_matrix_line", "set_matrix_fill",
        "set_matrix_character", "set_matrix_rotation", "clear_matrix",
        "get_acceleration", "get_vertical_acceleration", "get_orientation", "get_gyroscope",
        "get_velocity", "get_location", "get_distance", "get_speed", "get_heading",
        "get_luminosity", "get_compass_direction",
        "start_ir_broadcast", "stop_ir_broadcast", "start_ir_follow", "stop_ir_follow",
        "start_ir_evade", "stop_ir_evade", "send_ir_message",
    ]
    color_first = {"set_front_led", "set_matrix_character"}
    color_last = {"set_matrix_pixel", "set_matrix_line", "set_matrix_fill"}

    for name in passthrough:
        fn = getattr(backend, name, None)
        if fn is None:
            continue
        if name in color_last:
            g[name] = (lambda f: lambda *a: f(*a[:-1], color_arg(a[-1])))(fn)
        elif name == "set_front_led":
            g[name] = (lambda f: lambda c: f(color_arg(c)))(fn)
        elif name in color_first:
            g[name] = (lambda f: lambda ch, c: f(ch, color_arg(c)))(fn)
        else:
            g[name] = fn
    return g


def load_program(source: str, backend: Any, filename: str = "<program>") -> dict[str, Any]:
    """Execute a program's top level and return its namespace."""
    g = build_globals(backend)
    exec(compile(source, filename, "exec"), g)
    if not inspect.iscoroutinefunction(g.get("start_program")):
        raise ValueError(f"{filename}: expected `async def start_program():`")
    return g


async def run_program(path: str | Path, backend: Any, seconds: float | None = None) -> None:
    """Run an Edu-app program (``.py`` or ``.lab``) until it returns, exits, or ``seconds`` pass."""
    path = Path(path)
    if path.suffix == ".lab":
        from . import lab

        source = lab.read(path).code
    else:
        source = path.read_text(encoding="utf-8")
    g = load_program(source, backend, str(path))
    try:
        if seconds is None:
            await g["start_program"]()
        else:
            await backend.run_for(g["start_program"](), seconds)
    except ProgramExit:
        pass
    finally:
        backend.stop_roll(None)


def run(path: str | Path, backend: Any, seconds: float | None = None) -> None:
    asyncio.run(run_program(path, backend, seconds))
