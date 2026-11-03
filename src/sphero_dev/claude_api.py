"""A standard-library Claude API client, for where the ``anthropic`` SDK can't go (iOS).

:class:`ApiClient` stands in for ``anthropic.Anthropic()`` in
:class:`~sphero_dev.ask.Conversation`, like ``claude_code.ClaudeCodeClient``:
it has ``client.beta.messages.create(**kwargs)``, and returns the response as
attribute objects (``response.content[0].type`` ...). Content blocks keep every
field the API sent (thinking signatures included), so they go back unchanged
in the next request.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from types import SimpleNamespace
from typing import Any, Callable

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT_S = 600


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _ns(obj: Any) -> Any:
    """JSON into attribute objects, like the SDK's models. A tool call's ``input``
    stays a dict, as in the SDK."""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: v if k == "input" else _ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_ns(v) for v in obj]
    return obj


def _plain(obj: Any) -> Any:
    """Attribute objects (from earlier responses) back into JSON-able dicts."""
    if isinstance(obj, SimpleNamespace):
        return {k: _plain(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def _ssl_context() -> ssl.SSLContext:
    """Verify with certifi's CA list when it's there (iOS Python has no system one)."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


Transport = Callable[[str, dict[str, str], bytes], tuple[int, bytes]]


def urllib_transport(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=_ssl_context()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class ApiClient:
    def __init__(self, api_key: str, transport: Transport = urllib_transport,
                 url: str = API_URL):
        self.api_key, self.transport, self.url = api_key, transport, url
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))
        self.messages = self.beta.messages

    def create(self, *, betas: list[str] | None = None, **kwargs: Any) -> Any:
        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION,
                   "content-type": "application/json"}
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        status, body = self.transport(self.url, headers, json.dumps(_plain(kwargs)).encode())
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            data = {}
        if status != 200:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            raise ApiError(status, err.get("message") or f"HTTP {status}")
        return _ns(data)
