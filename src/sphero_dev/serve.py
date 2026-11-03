"""``sphero-dev serve``: the HTTP API behind the iPad app (``ios/``).

The computer running this does the work: it talks to Claude (through the
``claude`` CLI or the API, like ``sphero-dev ask``), runs the simulator, and
drives the robot over Bluetooth. The app only sends text and shows replies.

Every reply is a list of messages, each made of parts the app knows how to
draw::

    {"type": "text",  "text": "..."}
    {"type": "code",  "language": "python", "title": "...", "code": "..."}
    {"type": "chart", "title": "...", "kind": "path" | "line",
     "x_label": "...", "y_label": "...",
     "series": [{"name": "...", "points": [[x, y], ...]}]}
    {"type": "table", "title": "...", "columns": ["..."], "rows": [["..."]]}

Endpoints (all need ``Authorization: Bearer <token>``)::

    GET  /health                           -> {"ok": true, "robot": ..., ...}
    POST /chat {"conversation": id?, "text"} -> {"conversation": id, "messages": [...]}
    POST /run  {"conversation": id}        -> {"messages": [...]}  (runs the last program)
    POST /stop                             -> {"stopping": bool}
    GET  /program.lab?conversation=id      -> the last program as a Sphero Edu .lab file

The token is made on first start and kept in ``~/.config/sphero-dev/serve-token``.
"""

from __future__ import annotations

import argparse
import json
import secrets
import ssl
import sys
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import lab
from .ask import AskError, Conversation, Proposal

TOKEN_FILE = Path.home() / ".config" / "sphero-dev" / "serve-token"
MAX_BODY = 64 * 1024


def load_token(path: Path = TOKEN_FILE) -> str:
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(18)
    path.write_text(token + "\n")
    path.chmod(0o600)
    return token


# --- turning results into message parts ------------------------------------

def text(t: str) -> dict[str, Any]:
    return {"type": "text", "text": t}


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
    return {"role": "assistant", "parts": parts}


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
    return {"role": "assistant", "parts": parts}


# --- state -------------------------------------------------------------------

@dataclass
class Session:
    convo: Conversation
    proposal: Proposal | None = None
    last_run: Any = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class App:
    """Everything the handler needs; ``make_client`` and ``run_robot`` are swappable for tests."""

    def __init__(self, make_client: Callable[[], Any], run_robot: Callable[..., Any],
                 robot: str | None, seconds: float, max_speed: int, space: float | None,
                 model: str, effort: str, token: str):
        self.make_client, self.run_robot = make_client, run_robot
        self.robot, self.seconds, self.max_speed, self.space = robot, seconds, max_speed, space
        self.model, self.effort, self.token = model, effort, token
        self.sessions: dict[str, Session] = {}
        self.robot_lock = threading.Lock()
        self.stop_event: threading.Event | None = None

    def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        msg = str(body.get("text", "")).strip()
        if not msg:
            raise BadRequest("text is empty")
        cid = body.get("conversation")
        if cid is not None and cid not in self.sessions:
            raise BadRequest("unknown conversation (the server may have restarted)", 404)
        if cid is None:
            cid = uuid.uuid4().hex
            convo = Conversation(self.make_client(), max_speed=self.max_speed,
                                 seconds=self.seconds, space_cm=self.space, effort=self.effort,
                                 model=self.model)
            self.sessions[cid] = Session(convo)
        sess = self.sessions[cid]
        notes: list[str] = []
        with sess.lock:
            sess.convo.status = notes.append
            if sess.last_run is not None:
                msg = (f"I ran it on the real robot. {sess.last_run.summary}\n"
                       f"{sess.last_run.details}\n\n{msg}")
                sess.last_run = None
            try:
                reply = sess.convo.send(msg)
            except AskError as e:
                return {"conversation": cid, "messages": [{"role": "assistant",
                                                           "parts": [text(str(e))]}]}
        messages = []
        if notes:
            messages.append({"role": "status", "parts": [text("\n".join(notes))]})
        if reply.proposal is None:
            messages.append({"role": "assistant", "parts": [text(reply.text)]})
        else:
            sess.proposal = reply.proposal
            messages.append(proposal_message(reply.proposal))
        return {"conversation": cid, "messages": messages}

    def run(self, body: dict[str, Any]) -> dict[str, Any]:
        sess = self.sessions.get(body.get("conversation", ""))
        if sess is None or sess.proposal is None:
            raise BadRequest("no program to run in this conversation yet", 404)
        if not self.robot_lock.acquire(blocking=False):
            raise BadRequest("the robot is already running a program", 409)
        try:
            self.stop_event = threading.Event()
            try:
                result = self.run_robot(sess.proposal.code, self.robot, self.seconds,
                                        self.max_speed, "program.py", stop=self.stop_event)
            except Exception as e:  # no robot found, Bluetooth off, ...
                return {"messages": [{"role": "assistant", "parts": [text(
                    f"Couldn't run it on the robot: {type(e).__name__}: {e}")]}]}
            sess.last_run = result
            return {"messages": [run_message(result)]}
        finally:
            self.stop_event = None
            self.robot_lock.release()

    def stop(self) -> dict[str, Any]:
        ev = self.stop_event
        if ev is not None:
            ev.set()
        return {"stopping": ev is not None}

    def program_lab(self, cid: str) -> tuple[str, bytes]:
        sess = self.sessions.get(cid)
        if sess is None or sess.proposal is None:
            raise BadRequest("no program in this conversation yet", 404)
        p = sess.proposal
        data = lab.dumps(lab.LabProgram(name=p.title, code=p.code)).encode("utf-8")
        name = "".join(c if c.isalnum() else "_" for c in p.title.lower()).strip("_")
        return f"{name or 'program'}.lab", data


class BadRequest(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

        def _send(self, status: int, data: bytes, ctype: str,
                  extra: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: int, obj: Any) -> None:
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _authorized(self) -> bool:
            got = self.headers.get("Authorization", "")
            if secrets.compare_digest(got.encode(), f"Bearer {app.token}".encode()):
                return True
            self._json(401, {"error": "wrong or missing token"})
            return False

        def _body(self) -> dict[str, Any]:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise BadRequest("request too large", 413)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                raise BadRequest("body isn't JSON") from None
            if not isinstance(body, dict):
                raise BadRequest("body must be a JSON object")
            return body

        def _handle(self, fn: Callable[[], None]) -> None:
            if not self._authorized():
                return
            try:
                fn()
            except BadRequest as e:
                self._json(e.status, {"error": str(e)})
            except Exception as e:  # keep the server up; tell the app what broke
                self.log_error("%s: %s", type(e).__name__, e)
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

        def do_GET(self) -> None:
            url = urlparse(self.path)

            def go() -> None:
                if url.path == "/health":
                    self._json(200, {"ok": True, "robot": app.robot, "seconds": app.seconds,
                                     "max_speed": app.max_speed, "space_cm": app.space,
                                     "model": app.model})
                elif url.path == "/program.lab":
                    cid = parse_qs(url.query).get("conversation", [""])[0]
                    name, data = app.program_lab(cid)
                    self._send(200, data, "application/octet-stream",
                               {"Content-Disposition": f'attachment; filename="{name}"'})
                else:
                    raise BadRequest("not found", 404)
            self._handle(go)

        def do_POST(self) -> None:
            path = urlparse(self.path).path

            def go() -> None:
                if path == "/chat":
                    self._json(200, app.chat(self._body()))
                elif path == "/run":
                    self._json(200, app.run(self._body()))
                elif path == "/stop":
                    self._json(200, app.stop())
                else:
                    raise BadRequest("not found", 404)
            self._handle(go)

    return Handler


class TLSServer(ThreadingHTTPServer):
    """HTTPS. The TLS handshake runs in each request's thread, and the certificate is
    reloaded when its file changes, so a renewal needs no restart."""

    def __init__(self, address: tuple[str, int], handler: Any, cert: str, key: str):
        self.cert, self.key = cert, key
        self._ctx_lock = threading.Lock()
        self._load()
        super().__init__(address, handler)

    def _mtimes(self) -> tuple[float, float]:
        return Path(self.cert).stat().st_mtime, Path(self.key).stat().st_mtime

    def _load(self) -> None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(self.cert, self.key)
        self.ctx, self._loaded = ctx, self._mtimes()

    def _context(self) -> ssl.SSLContext:
        with self._ctx_lock:
            try:
                if self._mtimes() != self._loaded:
                    self._load()
                    sys.stderr.write("Reloaded the TLS certificate.\n")
            except (OSError, ssl.SSLError) as e:  # mid-renewal; keep the old one
                sys.stderr.write(f"Couldn't reload the certificate: {e}\n")
            return self.ctx

    def finish_request(self, request: Any, client_address: Any) -> None:
        request.settimeout(60)
        try:
            tls = self._context().wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return  # a scanner, or a client that doesn't trust the certificate
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            tls.close()


def _lan_addresses() -> list[str]:
    import socket

    addrs = set()
    try:  # the address used to reach the internet is usually the LAN one
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET; nothing is sent
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(addrs) or ["<this computer's IP>"]


def serve_main(args: argparse.Namespace) -> int:
    from . import claude_code
    from .cli import run_on_robot

    via = args.via
    if via == "auto":
        via = "claude-code" if claude_code.available() else "api"
    if via == "claude-code":
        if not claude_code.available():
            print("--via claude-code needs the `claude` CLI on PATH, logged in.", file=sys.stderr)
            return 1
        make_client: Callable[[], Any] = claude_code.ClaudeCodeClient
    else:
        try:
            import anthropic
        except ImportError:
            print("--via api needs the Anthropic SDK: pip install 'sphero-dev[ai]'",
                  file=sys.stderr)
            return 1
        make_client = anthropic.Anthropic

    app = App(make_client, run_on_robot, args.robot, args.seconds, args.max_speed, args.space,
              args.model, args.effort, load_token())
    if bool(args.cert) != bool(args.key):
        print("--cert and --key go together.", file=sys.stderr)
        return 1
    if args.cert:
        server: ThreadingHTTPServer = TLSServer((args.host, args.port), make_handler(app),
                                                args.cert, args.key)
        scheme = "https"
    else:
        server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
        scheme = "http"
    server.daemon_threads = True
    print(f"Serving the Sphero app API over {scheme.upper()} on port {args.port} "
          f"(Claude via {via}).")
    print("In the app's Settings, enter:")
    hosts = ([args.name] if args.name
             else _lan_addresses() if args.host in ("0.0.0.0", "") else [args.host])
    for h in hosts:
        print(f"  Server: {scheme}://{h}:{args.port}")
    if scheme == "http":
        print("  (Plain HTTP: anyone on this network can read the traffic, token included. "
              "See ios/README.md for HTTPS.)")
    print(f"  Token:  {app.token}")
    print("Ctrl-C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        app.stop()
        print("\nStopped.")
    finally:
        server.server_close()
    return 0
