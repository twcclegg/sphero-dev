"""Run ``sphero-dev ask`` through the Claude Code CLI instead of the API.

:class:`ClaudeCodeClient` stands in for ``anthropic.Anthropic()``: it has the
one method :class:`~sphero_dev.ask.Conversation` calls,
``client.beta.messages.create(...)``. Each call runs ``claude -p``, which
bills the user's Claude subscription (whatever ``claude`` is logged in as)
rather than an API key.

``claude -p`` can't call our tools, so Claude answers every turn with a JSON
object (``--json-schema``) naming the tool it wants and its arguments. We
turn that back into a ``tool_use`` block, and send tool results as the next
user message of the same session (``--resume``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from types import SimpleNamespace
from typing import Any

from .ask import AskError

TIMEOUT_S = 600

PROTOCOL = """

# Calling tools in this session

You can't call tools directly here. Answer every turn with the JSON object \
the schema describes:

- To call `simulate`, set "tool" to "simulate" and fill "code" and "seconds".
- To call `propose_program`, set "tool" to "propose_program" and fill \
"title", "summary" and "code".
- To answer in plain text (only to ask the user a question), set "tool" to \
"none" and put the message in "say".

"say" is a short note shown to the user while you work; it may be empty. \
The tool's result comes back as the next message.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "say": {"type": "string"},
        "tool": {"type": "string", "enum": ["simulate", "propose_program", "none"]},
        "code": {"type": "string"},
        "seconds": {"type": "integer"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["say", "tool"],
}

TOOL_ARGS = {"simulate": ("code", "seconds"), "propose_program": ("title", "summary", "code")}


def available() -> bool:
    return shutil.which("claude") is not None


def _render(content: Any) -> str:
    """A user message (text and tool results) as plain text for ``claude -p``."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if block["type"] == "tool_result":
            label = "error" if block.get("is_error") else "result"
            parts.append(f"[tool {label}]\n{block['content']}")
        elif block["type"] == "text":
            parts.append(block["text"])
    return "\n\n".join(parts)


class _Messages:
    def __init__(self, owner: ClaudeCodeClient):
        self._owner = owner

    def create(self, *, model: str, system: str, messages: list[dict[str, Any]],
               output_config: dict[str, Any] | None = None, **_: Any) -> Any:
        return self._owner._turn(model, system, messages[-1]["content"],
                                 (output_config or {}).get("effort"))


class ClaudeCodeClient:
    """Enough of ``anthropic.Anthropic()`` for :class:`~sphero_dev.ask.Conversation`."""

    def __init__(self, command: str = "claude"):
        self.command = command
        self.session_id: str | None = None
        self.beta = SimpleNamespace(messages=_Messages(self))
        self._workdir = tempfile.mkdtemp(prefix="sphero-dev-ask-")

    def _turn(self, model: str, system: str, content: Any, effort: str | None) -> Any:
        cmd = [self.command, "-p", "--model", model, "--output-format", "json",
               "--json-schema", json.dumps(SCHEMA), "--tools", "", "--strict-mcp-config",
               "--setting-sources", "", "--disable-slash-commands"]
        if effort:
            cmd += ["--effort", effort]
        if self.session_id is None:
            self.session_id = str(uuid.uuid4())
            cmd += ["--session-id", self.session_id, "--system-prompt", system + PROTOCOL]
        else:
            cmd += ["--resume", self.session_id]
        # Without an API key in its environment, claude uses its own login.
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        try:
            proc = subprocess.run(cmd, input=_render(content), capture_output=True, text=True,
                                  env=env, cwd=self._workdir, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise AskError(f"claude -p took longer than {TIMEOUT_S} s.") from None
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise AskError(f"claude -p failed (exit {proc.returncode}): "
                           f"{(proc.stderr or proc.stdout).strip()[:500]}") from None
        if out.get("is_error") or out.get("subtype") != "success":
            if out.get("stop_reason") == "refusal":
                return SimpleNamespace(stop_reason="refusal", content=[])
            raise AskError(f"claude -p failed: {out.get('result') or out.get('subtype')}")
        reply = out.get("structured_output")
        if not isinstance(reply, dict):
            # No structured output: treat the text as a plain reply.
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=out["result"])])
        blocks = []
        if reply.get("say"):
            blocks.append(SimpleNamespace(type="text", text=reply["say"]))
        tool = reply.get("tool")
        if tool in TOOL_ARGS:
            args = {k: reply[k] for k in TOOL_ARGS[tool] if k in reply}
            blocks.append(SimpleNamespace(type="tool_use", id=f"call_{uuid.uuid4().hex[:8]}",
                                          name=tool, input=args))
        return SimpleNamespace(stop_reason="tool_use" if tool in TOOL_ARGS else "end_turn",
                               content=blocks)
