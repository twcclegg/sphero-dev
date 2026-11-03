"""Runs `sphero-dev serve` with a scripted Claude and a fake robot, for the Swift client's
live test: python tests/serve_fixture.py PORT TOKEN, then
SPHERO_TEST_SERVER=http://127.0.0.1:PORT SPHERO_TEST_TOKEN=TOKEN swift test (in ios/SpheroChatCore).
"""

import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_ask import GOOD, FakeClient, msg, tool  # noqa: E402
from test_serve import FakeRobot  # noqa: E402

from sphero_dev import serve  # noqa: E402


def client():
    return FakeClient(msg(tool("propose_program", title="Forward", summary="Goes.", code=GOOD)))


if __name__ == "__main__":
    port, token = int(sys.argv[1]), sys.argv[2]
    app = serve.App(client, FakeRobot(), None, 5.0, 120, None, "fake", "low", token)
    ThreadingHTTPServer(("127.0.0.1", port), serve.make_handler(app)).serve_forever()
