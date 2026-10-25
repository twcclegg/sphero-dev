"""Backends that Edu-app programs run against: a real robot or a simulator."""

from __future__ import annotations

import asyncio
import inspect
import math
from dataclasses import dataclass, field
from typing import Any, Callable


async def _call_handler(handler: Callable[..., Any], args: tuple) -> None:
    n = len(inspect.signature(handler).parameters)
    result = handler(*args[:n])
    if inspect.isawaitable(result):
        await result


class RobotBackend:
    """Drives a real robot through spherov2's ``SpheroEduAPI``.

    ``api`` must already be entered (``with SpheroEduAPI(toy) as api``).
    """

    def __init__(self, api: Any):
        self.api = api
        self._loop: asyncio.AbstractEventLoop | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.api, name)

    @staticmethod
    def color(r: int, g: int, b: int) -> Any:
        from spherov2.types import Color

        return Color(r, g, b)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def raw_motor(self, left: int, right: int, duration: float) -> None:
        await asyncio.to_thread(self.api.raw_motor, left, right, duration)

    def register_event(self, name: str, handler: Callable[..., Any]) -> None:
        from spherov2.sphero_edu import EventType

        loop = asyncio.get_running_loop()

        # spherov2 calls listeners on a new thread as listener(api, *args).
        def listener(_api: Any, *args: Any) -> None:
            asyncio.run_coroutine_threadsafe(_call_handler(handler, args), loop)

        self.api.register_event(EventType[name], listener)

    async def run_for(self, coro: Any, seconds: float) -> None:
        try:
            await asyncio.wait_for(coro, seconds)
        except asyncio.TimeoutError:
            pass


class _TimeUp(Exception):
    pass


@dataclass
class SimBackend:
    """A rough 2D simulator with a virtual clock.

    It's for checking program logic without a robot, not for predicting real
    behaviour. Assumptions (not measured): ground speed is
    ``cm_per_unit * speed`` and approaches it with time constant ``tau``;
    the robot points exactly where it's told, instantly; no slipping.

    ``delay`` advances virtual time, so a 60 s program runs in well under a
    second. ``trace`` holds ``(t, x, y, heading, speed_cm_s)`` samples.
    """

    cm_per_unit: float = 0.7
    tau: float = 0.25
    dt: float = 0.01
    sample_every: float = 0.05
    log: Callable[[str], None] | None = None

    t: float = 0.0
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    distance: float = 0.0
    heading: int = 0
    speed: int = 0
    trace: list[tuple[float, float, float, int, float]] = field(default_factory=list)
    _limit: float | None = None
    _next_sample: float = 0.0

    # --- clock ---------------------------------------------------------
    async def sleep(self, seconds: float) -> None:
        end = self.t + max(0.0, seconds)
        if self._limit is not None:
            end = min(end, self._limit)
        while self.t < end - 1e-9:
            self._step(min(self.dt, end - self.t))
        await asyncio.sleep(0)
        if self._limit is not None and self.t >= self._limit - 1e-9:
            raise _TimeUp

    async def run_for(self, coro: Any, seconds: float) -> None:
        self._limit = self.t + seconds
        try:
            await coro
        except _TimeUp:
            pass
        finally:
            self._limit = None

    def _step(self, dt: float) -> None:
        target = self.cm_per_unit * self.speed
        self.v += (target - self.v) * min(1.0, dt / self.tau)
        h = math.radians(self.heading)
        self.x += self.v * math.sin(h) * dt
        self.y += self.v * math.cos(h) * dt
        self.distance += abs(self.v) * dt
        self.t += dt
        if self.t >= self._next_sample:
            self.trace.append((round(self.t, 3), self.x, self.y, self.heading, self.v))
            self._next_sample += self.sample_every

    def _say(self, msg: str) -> None:
        if self.log:
            self.log(f"[{self.t:7.2f}s] {msg}")

    # --- commands --------------------------------------------------------
    @staticmethod
    def color(r: int, g: int, b: int) -> tuple[int, int, int]:
        return (r, g, b)

    def set_speed(self, speed: int) -> None:
        self.speed = max(-255, min(255, speed))
        self._say(f"set_speed({self.speed})")

    def set_heading(self, heading: int) -> None:
        self.heading = heading % 360

    def stop_roll(self, heading: int | None = None) -> None:
        if heading is not None:
            self.heading = heading % 360
        self.speed = 0
        self._say("stop_roll()")

    async def raw_motor(self, left: int, right: int, duration: float) -> None:
        # Approximation: average power as speed, no turning.
        self.speed = (left + right) // 2
        await self.sleep(duration)
        self.speed = 0

    def register_event(self, name: str, handler: Callable[..., Any]) -> None:
        self._say(f"register_event({name}) (events aren't simulated)")

    # --- sensors ---------------------------------------------------------
    def get_velocity(self) -> dict[str, float]:
        h = math.radians(self.heading)
        return {"x": self.v * math.sin(h), "y": self.v * math.cos(h)}

    def get_location(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}

    def get_distance(self) -> float:
        return self.distance

    def get_speed(self) -> int:
        return self.speed

    def get_heading(self) -> int:
        return self.heading

    def __getattr__(self, name: str) -> Any:
        # Lights, matrix, IR and other sensors: accept and log, do nothing.
        if name.startswith("_"):
            raise AttributeError(name)

        def noop(*args: Any) -> None:
            self._say(f"{name}{args}")

        return noop
