"""The Python half of the iOS app, with fakes for Claude, Bluetooth and the robot."""

import json
import math
import random
import sys
from types import SimpleNamespace as NS

import pytest
from test_ask import CRASHES, GOOD

from sphero_dev import app, ask, claude_api, ios_adapter, lab, numpy_lite
from sphero_dev.cli import RobotRun

# --- numpy_lite ----------------------------------------------------------------


def test_numpy_lite_matches_numpy_for_vertical_acceleration():
    np = pytest.importorskip("numpy")
    euler = pytest.importorskip("transforms3d.euler")
    rng = random.Random(1)
    for _ in range(200):
        rpy = [rng.uniform(-180, 180) for _ in range(3)]
        acc = [rng.uniform(-2, 2) for _ in range(3)]
        vec = (acc[0], -acc[2], acc[1])
        r = euler.euler2mat(*np.deg2rad(rpy), axes="szxy")
        want = -np.matmul(np.linalg.inv(r), vec)[1]
        r2 = numpy_lite.euler2mat(*numpy_lite.deg2rad(rpy), axes="szxy")
        got = -numpy_lite.matmul(numpy_lite.inv(r2), vec)[1]
        assert math.isclose(got, want, abs_tol=1e-9)


def test_numpy_lite_installs_only_when_numpy_is_missing(monkeypatch):
    assert numpy_lite.install() is False  # the real numpy is here
    for name in ("numpy", "transforms3d", "transforms3d.euler"):
        monkeypatch.setitem(sys.modules, name, None)  # makes `import name` fail
    assert numpy_lite.install() is True
    import numpy
    from transforms3d.euler import euler2mat

    assert math.isclose(numpy.deg2rad([180])[0], math.pi)
    assert euler2mat is numpy_lite.euler2mat


# --- claude_api ------------------------------------------------------------------


class FakeTransport:
    """Answers with scripted Messages API JSON and records each request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, headers, body):
        self.requests.append((url, headers, json.loads(body)))
        status, payload = self.responses.pop(0)
        return status, json.dumps(payload).encode()


def api_msg(*blocks, stop="tool_use"):
    return 200, {"id": "msg", "type": "message", "role": "assistant", "content": list(blocks),
                 "stop_reason": stop, "usage": {}}


def tool_use(id_, name, **args):
    return {"type": "tool_use", "id": id_, "name": name, "input": args}


def test_api_client_drives_a_conversation():
    transport = FakeTransport(
        api_msg({"type": "thinking", "thinking": "hm", "signature": "sig"},
                tool_use("t1", "simulate", code=GOOD, seconds=3)),
        api_msg(tool_use("t2", "propose_program", title="Forward", summary="s", code=GOOD)),
    )
    client = claude_api.ApiClient("sk-test", transport=transport)
    reply = ask.Conversation(client, status=lambda s: None).send("drive forward")
    assert reply.proposal.title == "Forward"

    url, headers, body = transport.requests[0]
    assert url == claude_api.API_URL
    assert headers["x-api-key"] == "sk-test"
    assert headers["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert "betas" not in body and body["model"] == ask.MODEL
    # The thinking block went back verbatim, signature included.
    _, _, second = transport.requests[1]
    assert second["messages"][1]["content"][0] == {"type": "thinking", "thinking": "hm",
                                                   "signature": "sig"}
    assert second["messages"][2]["content"][0]["type"] == "tool_result"


def test_api_client_raises_api_errors():
    transport = FakeTransport((401, {"type": "error", "error": {"type": "authentication_error",
                                                                "message": "invalid x-api-key"}}))
    with pytest.raises(claude_api.ApiError) as e:
        claude_api.ApiClient("bad", transport=transport).create(model="m", messages=[])
    assert e.value.status == 401 and "invalid x-api-key" in str(e.value)


# --- ios_adapter -----------------------------------------------------------------


class FakeBridge:
    def __init__(self):
        self.calls = []

    def scan(self, timeout):
        self.calls.append(("scan", timeout))
        return [{"name": "BP-5FBB", "address": "UUID-1"}, {"name": "SB-1234", "address": "U2"},
                {"address": "U3"}]

    def connect(self, address):
        self.calls.append(("connect", address))

    def disconnect(self, address):
        self.calls.append(("disconnect", address))

    def subscribe(self, address, uuid):
        self.calls.append(("subscribe", address, uuid))

    def write(self, address, uuid, data):
        self.calls.append(("write", address, uuid, data))


@pytest.fixture
def bridge():
    b = FakeBridge()
    ios_adapter.set_bridge(b)
    yield b
    ios_adapter.set_bridge(None)


def test_spherov2_scanner_finds_a_bolt_plus_through_the_bridge(bridge):
    from spherov2 import scanner

    from sphero_dev.toys import BOLTPlus

    toy = scanner.find_toy(toy_name="BP-5FBB", toy_types=[BOLTPlus],
                           adapter=ios_adapter.IOSAdapter)
    assert isinstance(toy, BOLTPlus) and toy.address == "UUID-1"


def test_adapter_passes_writes_and_notifications(bridge):
    got = []
    a = ios_adapter.IOSAdapter("UUID-1")
    a.set_callback("00010002-574F-4F20-5370-6865726F2121", lambda c, d: got.append((c, d)))
    a.write("00010002-574f-4f20-5370-6865726f2121", bytearray(b"\x8d\x01"))
    ios_adapter.on_notify("UUID-1", "00010002-574f-4f20-5370-6865726f2121", b"\x8d\xd8")
    ios_adapter.on_notify("OTHER", "00010002-574f-4f20-5370-6865726f2121", b"\x00")
    a.close()
    ios_adapter.on_notify("UUID-1", "00010002-574f-4f20-5370-6865726f2121", b"\x8d")
    assert got == [("00010002-574f-4f20-5370-6865726f2121", bytearray(b"\x8d\xd8"))]
    assert bridge.calls[0] == ("connect", "UUID-1")
    assert ("write", "UUID-1", "00010002-574f-4f20-5370-6865726f2121", b"\x8d\x01") in bridge.calls
    assert bridge.calls[-1] == ("disconnect", "UUID-1")


def test_adapter_without_bridge_says_why():
    with pytest.raises(RuntimeError, match="iOS app"):
        ios_adapter.IOSAdapter.scan_toys()


# --- simulating in a thread (iOS can't start processes) --------------------------


@pytest.fixture
def in_thread(monkeypatch):
    monkeypatch.setattr(ask, "SIM_IN_THREAD", True)
    monkeypatch.setattr(ask, "SIM_WALL_CLOCK_S", 2.0)


def test_thread_simulation_matches_process(in_thread):
    r = ask.simulate(GOOD, 3)
    assert r.ok and r.distance > 10 and r.trace
    assert not ask.simulate(CRASHES, 3).ok


def test_thread_simulation_stops_a_hung_program(in_thread):
    hung = "async def start_program():\n    while True:\n        x = 1\n"
    r = ask.simulate(hung, 5)
    assert not r.ok and "hung" in r.report
    # `except Exception` in the program can't swallow the watchdog.
    sneaky = ("async def start_program():\n    while True:\n        try:\n"
              "            x = 1\n        except Exception:\n            pass\n")
    assert "hung" in ask.simulate(sneaky, 5).report


# --- app: what Swift calls --------------------------------------------------------


class FakeRobot:
    def __init__(self):
        self.calls = []

    def __call__(self, code, robot, seconds, max_speed, filename, stop=None):
        self.calls.append((code, robot, seconds, max_speed, stop))
        samples = [(t / 4, 0.0, t * 10.0, 0, 40.0, 80) for t in range(12)]
        return RobotRun("Ran for 3.0 s (finished by itself).", "path...", samples)


def make_app(*responses):
    transport = FakeTransport(*responses)
    robot = FakeRobot()
    a = app.App(make_client=lambda s: claude_api.ApiClient(s.api_key, transport=transport),
                run_robot=robot)
    a.configure(app.Settings(api_key="sk", robot="BP-5FBB", seconds=5, max_speed=120,
                             space_cm=50))
    return a, transport, robot


def test_app_chat_run_follow_up_and_export():
    a, transport, robot = make_app(
        api_msg(tool_use("t1", "propose_program", title="Forward!", summary="Goes.", code=GOOD)),
        api_msg({"type": "text", "text": "Slower?"}, stop="end_turn"),
    )
    msgs = a.chat("drive forward")
    assert [m["role"] for m in msgs] == ["status", "assistant"]
    assert [p["type"] for p in msgs[-1]["parts"]][:3] == ["text", "code", "chart"]
    assert "50 cm of clear floor" in transport.requests[0][2]["messages"][0]["content"][-1]["text"]

    run = a.run()[0]["parts"]
    assert [p["type"] for p in run] == ["text", "chart", "chart", "table"]
    assert robot.calls[0][:4] == (GOOD, "BP-5FBB", 5, 120)

    assert a.chat("too fast")[-1]["parts"][0]["text"] == "Slower?"
    sent = transport.requests[1][2]["messages"][-1]["content"][-1]["text"]
    assert sent.startswith("I ran it on the real robot.") and sent.endswith("too fast")

    f = a.lab_file()
    assert f["name"] == "forward.lab" and lab.loads(f["content"]).code.strip() == GOOD.strip()


def test_app_recovers_from_a_failed_turn():
    a, transport, _ = make_app(
        (401, {"type": "error", "error": {"message": "invalid x-api-key"}}),
        api_msg({"type": "text", "text": "Hi"}, stop="end_turn"),
    )
    err = a.chat("hello")[0]
    assert err["role"] == "error" and "API key" in err["parts"][0]["text"]
    assert a.chat("hello again")[-1]["parts"][0]["text"] == "Hi"
    # The failed turn was dropped, so the history alternates properly.
    roles = [m["role"] for m in transport.requests[1][2]["messages"]]
    assert roles == ["user"]


def test_app_needs_a_key_and_a_program():
    a = app.App(make_client=lambda s: None, run_robot=FakeRobot())
    assert "API key" in a.chat("hi")[0]["parts"][0]["text"]
    assert a.run()[0]["role"] == "error"
    assert a.lab_file() is None and a.stop() is False


def test_entry_points_speak_json(monkeypatch):
    a, _, _ = make_app(api_msg({"type": "text", "text": "Hello"}, stop="end_turn"))
    monkeypatch.setattr(app, "_app", a)
    assert json.loads(app.configure(json.dumps({"api_key": "sk", "robot": "", "max_speed": 99,
                                                "unknown": 1}))) == {}
    assert a.settings.robot is None and a.settings.max_speed == 99
    out = json.loads(app.chat("hi"))
    assert out["messages"][-1]["parts"][0]["text"] == "Hello"
    assert json.loads(app.stop()) == {"stopping": False}
    assert json.loads(app.lab_file()) == {}
    monkeypatch.setattr(a, "chat", lambda m: NS().boom)  # an internal error
    assert "Internal error" in json.loads(app.chat("x"))["messages"][0]["parts"][0]["text"]
