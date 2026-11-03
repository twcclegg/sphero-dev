"""`sphero-dev serve` over real HTTP, with a fake Claude and a fake robot."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from test_ask import GOOD, FakeClient, msg, text, tool

from sphero_dev import lab, serve
from sphero_dev.cli import RobotRun


class FakeRobot:
    def __init__(self):
        self.calls = []

    def __call__(self, code, robot, seconds, max_speed, filename, stop=None):
        self.calls.append((code, max_speed, stop))
        samples = [(t / 4, 0.0, t * 10.0, 0, 40.0, 80) for t in range(12)]
        return RobotRun("Ran for 3.0 s (finished by itself).", "path...", samples)


@pytest.fixture
def server():
    responses = []
    robot = FakeRobot()
    app = serve.App(lambda: FakeClient(*responses), robot, None, 5.0, 120, 50.0,
                    "claude-sonnet-5-5", "low", "secret")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None, token="secret", raw=False):
        req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                return r.status, (data if raw else json.loads(data))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call, responses, robot, app
    httpd.shutdown()


def test_needs_token(server):
    call, *_ = server
    assert call("/health", token="wrong")[0] == 401
    status, body = call("/health")
    assert status == 200 and body["max_speed"] == 120 and body["space_cm"] == 50.0


def test_chat_run_and_follow_up(server):
    call, responses, robot, app = server
    responses += [
        msg(text("Drafting."), tool("simulate", code=GOOD, seconds=3)),
        msg(tool("propose_program", title="Forward", summary="Goes forward.", code=GOOD)),
        msg(text("Shall I slow it down?"), stop="end_turn"),
    ]
    status, body = call("/chat", {"text": "drive forward"})
    assert status == 200
    cid = body["conversation"]
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["status", "assistant"]
    kinds = [p["type"] for p in body["messages"][-1]["parts"]]
    assert kinds[:3] == ["text", "code", "chart"]
    code = body["messages"][-1]["parts"][1]
    assert code["language"] == "python" and code["code"] == GOOD.rstrip()
    chart = body["messages"][-1]["parts"][2]
    assert chart["kind"] == "path" and len(chart["series"][0]["points"]) > 2

    status, body = call("/run", {"conversation": cid})
    assert status == 200
    assert robot.calls[0][0] == GOOD and robot.calls[0][1] == 120
    parts = body["messages"][0]["parts"]
    assert [p["type"] for p in parts] == ["text", "chart", "chart", "table"]
    assert parts[3]["rows"][0][0] == "0.0" and len(parts[3]["rows"]) == 3

    status, lab_bytes = call(f"/program.lab?conversation={cid}", raw=True)
    assert status == 200 and lab.loads(lab_bytes.decode()).code.strip() == GOOD.strip()

    # The run's result goes to Claude with the next message.
    status, body = call("/chat", {"conversation": cid, "text": "too fast"})
    assert body["messages"][-1]["parts"][0]["text"] == "Shall I slow it down?"
    convo = app.sessions[cid].convo
    sent = convo.messages[-2]["content"][-1]["text"]
    assert sent.startswith("I ran it on the real robot.") and sent.endswith("too fast")
    assert "50 cm of clear floor" in convo.messages[0]["content"][-1]["text"]


def test_errors(server):
    call, *_ = server
    assert call("/chat", {"text": ""})[0] == 400
    assert call("/chat", {"conversation": "nope", "text": "hi"})[0] == 404
    assert call("/run", {"conversation": "nope"})[0] == 404
    assert call("/stop", {}) == (200, {"stopping": False})


def _self_signed(tmp_path, name):
    import shutil
    import subprocess

    if not shutil.which("openssl"):
        pytest.skip("needs the openssl command")
    cert, key = tmp_path / f"{name}.pem", tmp_path / f"{name}.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", f"/CN={name}", "-addext", f"subjectAltName=DNS:{name}",
                    "-keyout", str(key), "-out", str(cert)],
                   check=True, capture_output=True)
    return cert, key


def test_https_and_certificate_reload(tmp_path):
    import os
    import ssl

    cert, key = _self_signed(tmp_path, "localhost")
    app = serve.App(lambda: None, FakeRobot(), None, 5.0, 120, None, "m", "low", "secret")
    httpd = serve.TLSServer(("127.0.0.1", 0), serve.make_handler(app), str(cert), str(key))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"https://localhost:{httpd.server_address[1]}/health"

    def get(cafile):
        ctx = ssl.create_default_context(cafile=str(cafile))
        req = urllib.request.Request(url, headers={"Authorization": "Bearer secret"})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return json.loads(r.read())

    try:
        assert get(cert)["ok"]
        # Plain HTTP to the HTTPS port gets nowhere.
        with pytest.raises((urllib.error.URLError, ConnectionError)):
            urllib.request.urlopen(url.replace("https", "http"), timeout=5)
        # A renewed certificate is picked up without a restart.
        def presented():
            pem = ssl.get_server_certificate(("127.0.0.1", httpd.server_address[1]))
            return ssl.PEM_cert_to_DER_cert(pem)

        assert presented() == ssl.PEM_cert_to_DER_cert(cert.read_text())
        new_cert, new_key = _self_signed(tmp_path, "renewed")
        os.replace(new_key, key)
        os.replace(new_cert, cert)
        os.utime(cert, (1, 1))  # make sure the mtime differs even within a second
        assert presented() == ssl.PEM_cert_to_DER_cert(cert.read_text())
    finally:
        httpd.shutdown()
