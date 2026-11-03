"""What the iOS app (``ios/``) runs in its embedded Python: Claude, the simulator, the robot.

The Swift side draws the screens, does Bluetooth (through
:mod:`sphero_dev.ios_adapter`) and keeps the API key in the Keychain. It calls
the functions at the bottom of this module with JSON strings and gets JSON
strings back; they never raise.

Replies are lists of messages, each a list of parts the app knows how to draw::

    {"type": "text",  "text": "..."}
    {"type": "code",  "language": "python", "title": "...", "code": "..."}
    {"type": "chart", "title": "...", "kind": "path" | "line",
     "x_label": "...", "y_label": "...",
     "series": [{"name": "...", "points": [[x, y], ...]}]}
    {"type": "table", "title": "...", "columns": ["..."], "rows": [["..."]]}

Keep this in step with ``ios/SpheroChatCore/Sources/SpheroChatCore/Models.swift``.
"""

from __future__ import annotations

import json
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from . import lab
from .ask import MODEL, AskError, Conversation, Proposal

# --- turning results into message parts ------------------------------------


def text(t: str) -> dict[str, Any]:
    return {"type": "text", "text": t}


def message(role: str, *parts: dict[str, Any]) -> dict[str, Any]:
    return {"role": role, "parts": list(parts)}


def _thin(points: list[Any], most: int = 400) -> list[Any]:
    step = max(1, len(points) // most)
    return points[::step] + ([points[-1]] if points and (len(points) - 1) % step else [])


def path_chart(title: str, xy: list[tuple[float, float]]) -> dict[str, Any]:
    return {"type": "chart", "title": title, "kind": "path", "x_label": "x (cm, right)",
            "y_label": "y (cm, forward)",
            "series": [{"name": "path", "points": [[round(x, 1), round(y, 1)]
                                                   for x, y in _thin(xy)]}]}


def line_chart(title: str, y_label: str,
               series: dict[str, list[tuple[float, float]]]) -> dict[str, Any]:
    return {"type": "chart", "title": title, "kind": "line", "x_label": "time (s)",
            "y_label": y_label,
            "series": [{"name": name, "points": [[round(t, 2), round(v, 1)]
                                                 for t, v in _thin(pts)]}
                       for name, pts in series.items()]}


def proposal_message(p: Proposal) -> dict[str, Any]:
    parts = [text(f"**{p.title}**\n\n{p.summary}"),
             {"type": "code", "language": "python", "title": p.title, "code": p.code.rstrip()}]
    if p.sim_trace:
        parts.append(path_chart("Simulated path (rough: no slipping or collisions)",
                                [(x, y) for _t, x, y, _h, _v in p.sim_trace]))
    first = p.sim_report.splitlines()[:2]
    if first:
        parts.append(text("Simulator: " + " ".join(first)))
    return message("assistant", *parts)


def run_message(run: Any) -> dict[str, Any]:
    parts = [text(run.summary)]
    s = run.samples
    if s:
        parts.append(path_chart("Measured path", [(x, y) for _t, x, y, _h, _v, _c in s]))
        parts.append(line_chart("Speed", "cm/s",
                                {"measured (cm/s)": [(t, v) for t, _x, _y, _h, v, _c in s],
                                 "commanded (0-255)": [(t, c) for t, _x, _y, _h, _v, c in s]}))
        rows, next_t = [], 0.0
        for t, x, y, h, v, c in s:
            if t >= next_t:
                rows.append([f"{t:.1f}", f"{x:.0f}", f"{y:.0f}", str(h), f"{v:.0f}", str(c)])
                next_t += 1.0
        parts.append({"type": "table", "title": "Sensors, once a second",
                      "columns": ["t (s)", "x (cm)", "y (cm)", "heading", "speed (cm/s)",
                                  "commanded"],
                      "rows": rows})
    return message("assistant", *parts)


# --- the app's state ---------------------------------------------------------


@dataclass
class Settings:
    api_key: str = ""
    model: str = MODEL
    effort: str = "medium"
    robot: str | None = None  # e.g. "BP-5FBB"; None = first robot found
    seconds: float = 30.0
    max_speed: int = 150
    space_cm: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Settings:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        s = cls(**known)
        s.robot = s.robot or None
        return s


@dataclass
class App:
    """One conversation with Claude, plus the robot. ``make_client`` and ``run_robot``
    are swappable for tests."""

    make_client: Callable[[Settings], Any]
    run_robot: Callable[..., Any]
    settings: Settings = field(default_factory=Settings)
    convo: Conversation | None = None
    proposal: Proposal | None = None
    last_run: Any = None
    stop_event: threading.Event | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def configure(self, settings: Settings) -> None:
        changed = (settings.api_key, settings.model) != (self.settings.api_key,
                                                        self.settings.model)
        self.settings = settings
        if changed:
            self.convo = None  # a new client next time

    def new_conversation(self) -> None:
        self.convo, self.proposal, self.last_run = None, None, None

    def chat(self, msg: str) -> list[dict[str, Any]]:
        msg = msg.strip()
        if not msg:
            return []
        if not self.settings.api_key:
            return [message("error", text("Add your Anthropic API key in Settings first."))]
        with self._lock:
            if self.convo is None:
                s = self.settings
                self.convo = Conversation(self.make_client(s), max_speed=s.max_speed,
                                          seconds=s.seconds, space_cm=s.space_cm,
                                          effort=s.effort, model=s.model)
            notes: list[str] = []
            self.convo.status = notes.append
            if self.last_run is not None:
                msg = (f"I ran it on the real robot. {self.last_run.summary}\n"
                       f"{self.last_run.details}\n\n{msg}")
                self.last_run = None
            sent = len(self.convo.messages)
            try:
                reply = self.convo.send(msg)
            except Exception as e:
                # Forget the failed turn, so the next message starts cleanly.
                del self.convo.messages[sent:]
                self.convo._pending = []
                return [message("error", text(_describe(e)))]
        out = []
        if notes:
            out.append(message("status", text("\n".join(n.strip() for n in notes))))
        if reply.proposal is None:
            out.append(message("assistant", text(reply.text)))
        else:
            self.proposal = reply.proposal
            out.append(proposal_message(reply.proposal))
        return out

    def run(self) -> list[dict[str, Any]]:
        if self.proposal is None:
            return [message("error", text("There's no program to run yet."))]
        if self.stop_event is not None:
            return [message("error", text("The robot is already running a program."))]
        self.stop_event = threading.Event()
        s = self.settings
        try:
            result = self.run_robot(self.proposal.code, s.robot, s.seconds, s.max_speed,
                                    "program.py", stop=self.stop_event)
        except Exception as e:  # no robot found, Bluetooth off, ...
            return [message("error", text(f"Couldn't run it on the robot: {e}"))]
        finally:
            self.stop_event = None
        self.last_run = result
        return [run_message(result)]

    def stop(self) -> bool:
        ev = self.stop_event
        if ev is not None:
            ev.set()
        return ev is not None

    def lab_file(self) -> dict[str, str] | None:
        if self.proposal is None:
            return None
        p = self.proposal
        name = "".join(c if c.isalnum() else "_" for c in p.title.lower()).strip("_")
        return {"name": f"{name or 'program'}.lab",
                "content": lab.dumps(lab.LabProgram(name=p.title, code=p.code))}


def _describe(e: Exception) -> str:
    from .claude_api import ApiError

    if isinstance(e, AskError):
        return str(e)
    if isinstance(e, ApiError):
        if e.status == 401:
            return "Anthropic rejected the API key. Check it in Settings."
        if e.status == 429:
            return "Rate limited by the Claude API. Wait a minute and try again."
        return f"Claude API error {e.status}: {e}"
    if isinstance(e, OSError):
        return f"Couldn't reach the Claude API. Is the iPad online? ({e})"
    return f"{type(e).__name__}: {e}"


# --- entry points for Swift: JSON in, JSON out, never raise -----------------

def _api_client(settings: Settings) -> Any:
    from .claude_api import ApiClient

    return ApiClient(settings.api_key)


def _robot(*args: Any, **kwargs: Any) -> Any:
    from . import numpy_lite

    numpy_lite.install()  # before spherov2.sphero_edu is imported
    from .cli import run_on_robot
    from .ios_adapter import IOSAdapter

    return run_on_robot(*args, adapter=IOSAdapter, **kwargs)


_app = App(make_client=_api_client, run_robot=_robot)


def _guard(fn: Callable[[], Any]) -> str:
    try:
        return json.dumps(fn())
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"messages": [message("error", text(
            f"Internal error: {type(e).__name__}: {e}"))]})


def configure(settings_json: str) -> str:
    return _guard(lambda: _app.configure(Settings.from_dict(json.loads(settings_json))) or {})


def chat(msg: str) -> str:
    return _guard(lambda: {"messages": _app.chat(msg)})


def run() -> str:
    return _guard(lambda: {"messages": _app.run()})


def stop() -> str:
    return _guard(lambda: {"stopping": _app.stop()})


def new_conversation() -> str:
    return _guard(lambda: _app.new_conversation() or {})


def lab_file() -> str:
    return _guard(lambda: _app.lab_file() or {})
