"""`sphero-dev ask` through a scripted fake of `claude -p` (no network)."""

import json
from types import SimpleNamespace as NS

from sphero_dev import ask, claude_code

GOOD = "# Drives forward.\nasync def start_program():\n    set_speed(80)\n    await delay(2)\n"


class FakeClaude:
    """Replaces subprocess.run: returns scripted structured outputs, records each call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, cmd, input, env, **_):
        self.calls.append(NS(cmd=cmd, input=input, env=env))
        out = {"type": "result", "subtype": "success", "is_error": False,
               "result": "", "structured_output": self.replies.pop(0)}
        return NS(returncode=0, stdout=json.dumps(out), stderr="")


def test_tool_calls_round_trip_through_one_session(monkeypatch):
    fake = FakeClaude(
        {"say": "Drafting.", "tool": "simulate", "code": GOOD, "seconds": 5},
        {"say": "", "tool": "propose_program", "title": "Forward", "summary": "s", "code": GOOD},
    )
    monkeypatch.setattr(claude_code.subprocess, "run", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    convo = ask.Conversation(claude_code.ClaudeCodeClient(), status=lambda s: None)
    reply = convo.send("drive forward")

    assert reply.proposal.title == "Forward"
    first, second = fake.calls
    assert "--system-prompt" in first.cmd and "--session-id" in first.cmd
    assert first.cmd[first.cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert "drive forward" in first.input
    # The follow-up resumes the same session and carries the simulator's report.
    assert second.cmd[second.cmd.index("--resume") + 1] == \
        first.cmd[first.cmd.index("--session-id") + 1]
    assert "[tool result]" in second.input and "Travelled" in second.input
    # Never billed to an API key.
    assert "ANTHROPIC_API_KEY" not in first.env


def test_plain_reply_is_a_question(monkeypatch):
    fake = FakeClaude({"say": "How big?", "tool": "none"})
    monkeypatch.setattr(claude_code.subprocess, "run", fake)
    reply = ask.Conversation(claude_code.ClaudeCodeClient(), status=lambda s: None).send("x")
    assert reply.proposal is None and reply.text == "How big?"


def test_missing_code_goes_back_as_an_error(monkeypatch):
    fake = FakeClaude({"say": "", "tool": "simulate"},
                      {"say": "", "tool": "none"})
    monkeypatch.setattr(claude_code.subprocess, "run", fake)
    ask.Conversation(claude_code.ClaudeCodeClient(), status=lambda s: None).send("x")
    assert "[tool error]" in fake.calls[1].input and "needs code" in fake.calls[1].input
