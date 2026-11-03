"""Connects :mod:`sphero_dev.ios_adapter` to the iOS app's Bluetooth code.

The app builds a module, ``_sphero_ble``, into its embedded Python (see
``ios/SpheroChat/Python/PythonBridge.c``) and imports this module at start.
Importing it anywhere else does nothing.
"""

from __future__ import annotations

import json
from typing import Any

from . import ios_adapter


class ModuleBridge:
    """:class:`ios_adapter.Bridge` over ``_sphero_ble``, whose scan returns JSON."""

    def __init__(self, module: Any):
        self.m = module

    def scan(self, timeout: float) -> list[dict[str, str]]:
        return json.loads(self.m.scan(float(timeout)))

    def connect(self, address: str) -> None:
        self.m.connect(address)

    def disconnect(self, address: str) -> None:
        self.m.disconnect(address)

    def subscribe(self, address: str, uuid: str) -> None:
        self.m.subscribe(address, uuid)

    def write(self, address: str, uuid: str, data: bytes) -> None:
        self.m.write(address, uuid, bytes(data))


def install() -> bool:
    try:
        import _sphero_ble  # type: ignore[import-not-found]
    except ImportError:
        return False
    ios_adapter.set_bridge(ModuleBridge(_sphero_ble))
    return True


install()
