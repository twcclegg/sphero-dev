"""`sphero-dev ask` against a scripted fake of the Anthropic client (no network)."""

from types import SimpleNamespace as NS

import pytest

from sphero_dev import ask

GOOD = (
    "# Drives forward.\n"
    "async def start_program():\n"
    "    set_speed(80)\n"
    "    await delay(2)\n"
)
CRASHES = "async def start_program():\n    await delay(0.5)\n    1 / 0\n"


def text(t):
    return NS(type="text", text=t)


def tool(name, **args):
    tool.n += 1
    return NS(type="tool_use", id=f"tu_{tool.n}", name=name, input=args)


tool.n = 0


def msg(*blocks, stop="tool_use"):
    return NS(stop_reason=stop, content=list(blocks), stop_details=None)


class FakeClient:
    """Returns the scripted responses in order and records each request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        # Snapshot the messages: the conversation keeps appending to the list.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def convo(client, **kw):
    return ask.Conversation(client, status=lambda s: None, **kw)


def test_simulate_then_propose_returns_proposal():
    client = FakeClient(
        msg(text("Drafting."), tool("simulate", code=GOOD, seconds=5)),
        msg(tool("propose_program", title="Forward", summary="Goes forward.", code=GOOD)),
    )
    reply = convo(client).send("drive forward")
    assert reply.proposal.title == "Forward"
    assert "Travelled" in reply.proposal.sim_report

    first = client.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["thinking"] == {"type": "adaptive"}
    assert first["fallbacks"] == "default"
    assert "speed is capped at 255" in first["messages"][0]["content"][-1]["text"]
    # The simulator's report went back to Claude as a tool result.
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and not result["is_error"]
    assert "Travelled" in result["content"]


def test_follow_up_carries_owed_tool_result():
    client = FakeClient(
        msg(tool("propose_program", title="Forward", summary="s", code=GOOD)),
        msg(text("How far is too far?"), stop="end_turn"),
    )
    c = convo(client)
    c.send("drive forward")
    reply = c.send("it went too far")
    assert reply.proposal is None and reply.text == "How far is too far?"
    content = client.requests[1]["messages"][-1]["content"]
    assert content[0]["type"] == "tool_result"
    assert content[1] == {"type": "text", "text": "it went too far"}


def test_broken_proposal_goes_back_to_claude():
    client = FakeClient(
        msg(tool("propose_program", title="Bad", summary="s", code=CRASHES)),
        msg(tool("propose_program", title="Good", summary="s", code=GOOD)),
    )
    reply = convo(client).send("x")
    assert reply.proposal.title == "Good"
    rejected = client.requests[1]["messages"][-1]["content"][0]
    assert rejected["is_error"] and "ZeroDivisionError" in rejected["content"]


def test_refusal_raises():
    client = FakeClient(msg(stop="refusal"))
    with pytest.raises(ask.AskError):
        convo(client).send("x")


@pytest.mark.parametrize("code, problem", [
    ("import math\nasync def start_program():\n    pass\n", "imports"),
    ("def start_program():\n    pass\n", "async def start_program"),
    ("async def start_program(:\n", "SyntaxError"),
])
def test_dialect_problems_are_reported(code, problem):
    result = ask.simulate(code, 5)
    assert not result.ok and problem in result.report


def test_hanging_program_is_stopped(monkeypatch):
    monkeypatch.setattr(ask, "SIM_WALL_CLOCK_S", 8.0)
    result = ask.simulate("async def start_program():\n    while True:\n        pass\n", 5)
    assert not result.ok and "hung" in result.report


def test_sim_respects_max_speed():
    code = "async def start_program():\n    set_speed(255)\n    await delay(3)\n"
    report = ask.simulate(code, 3, max_speed=100).report
    assert "Top ground speed 70 cm/s" in report


def test_system_prompt_includes_rules_and_reference():
    prompt = ask.system_prompt()
    assert "No imports" in prompt
    assert "def set_speed" in prompt  # stubs
    assert "# Sphero Edu API reference" in prompt


def test_cli_saves_and_quits(monkeypatch, tmp_path):
    anthropic = pytest.importorskip("anthropic")
    from sphero_dev import ask_cli
    from sphero_dev.cli import main

    client = FakeClient(msg(tool("propose_program", title="Forward!", summary="s", code=GOOD)))
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    answers = iter(["s", "q"])
    monkeypatch.setattr(ask_cli, "_input", lambda prompt: next(answers))
    assert main(["ask", "drive", "forward", "-o", str(tmp_path)]) == 0
    assert (tmp_path / "forward.py").read_text() == GOOD
    assert (tmp_path / "forward.lab").exists()
