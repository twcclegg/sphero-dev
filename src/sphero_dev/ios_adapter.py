"""A spherov2 Bluetooth adapter that goes through the iOS app's CoreBluetooth code.

spherov2 talks to Bluetooth through an adapter class with five operations
(see ``spherov2.adapter.bleak_adapter``). On iOS, where bleak doesn't run,
:class:`IOSAdapter` hands each one to a *bridge*: an object the app provides
with the same operations, implemented in Swift. Bytes come back through
``on_notify``, which the bridge calls from its own thread.

The bridge interface (all blocking, called from Python threads)::

    scan(timeout: float) -> list[{"name": str, "address": str}]
    connect(address: str) -> None            # raises on failure
    disconnect(address: str) -> None
    subscribe(address: str, uuid: str) -> None
    write(address: str, uuid: str, data: bytes) -> None   # with response

and the bridge calls ``ios_adapter.on_notify(address, uuid, data)`` for every
notification. :func:`set_bridge` installs it (the app does this at start).
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any, Callable, Protocol


class Bridge(Protocol):
    def scan(self, timeout: float) -> list[dict[str, str]]: ...
    def connect(self, address: str) -> None: ...
    def disconnect(self, address: str) -> None: ...
    def subscribe(self, address: str, uuid: str) -> None: ...
    def write(self, address: str, uuid: str, data: bytes) -> None: ...


_bridge: Bridge | None = None
_callbacks: dict[tuple[str, str], Callable[[Any, bytearray], None]] = {}
_lock = threading.Lock()


def set_bridge(bridge: Bridge | None) -> None:
    global _bridge
    _bridge = bridge


def bridge() -> Bridge:
    if _bridge is None:
        raise RuntimeError("No Bluetooth bridge: this runs inside the iOS app.")
    return _bridge


def on_notify(address: str, uuid: str, data: bytes) -> None:
    """Called by the app for each notification from the robot."""
    with _lock:
        cb = _callbacks.get((address, uuid.lower()))
    if cb is not None:
        cb(uuid, bytearray(data))


class IOSAdapter:
    @staticmethod
    def scan_toys(timeout: float = 5.0) -> list[SimpleNamespace]:
        return [SimpleNamespace(name=d.get("name"), address=d["address"])
                for d in bridge().scan(timeout)]

    @staticmethod
    def scan_toy(name: str, timeout: float = 5.0) -> SimpleNamespace | None:
        return next((t for t in IOSAdapter.scan_toys(timeout) if t.name == name), None)

    def __init__(self, address: str):
        self.address = address
        bridge().connect(address)

    def close(self, disconnect: bool = True) -> None:
        with _lock:
            for key in [k for k in _callbacks if k[0] == self.address]:
                del _callbacks[key]
        if disconnect:
            bridge().disconnect(self.address)

    def set_callback(self, uuid: str, cb: Callable[[Any, bytearray], None]) -> None:
        with _lock:
            _callbacks[(self.address, uuid.lower())] = cb
        bridge().subscribe(self.address, uuid)

    def write(self, uuid: str, data: bytes) -> None:
        bridge().write(self.address, uuid, bytes(data))
