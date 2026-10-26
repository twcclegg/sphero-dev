# The Sphero software ecosystem

What exists, what works, and what to use. Last reviewed October 2026.

## First-party (Sphero, Inc.)

| What | Robots | Notes |
|---|---|---|
| **Sphero Edu app** | All current robots | Draw, Blocks, JavaScript and Python. The easiest path. |
| [sdk.sphero.com](https://sdk.sphero.com/documentation/sdk-documents) | Mostly RVR | Public SDK site: RVR + Raspberry Pi / micro:bit / Arduino guides, the command reference, and the [v2 packet protocol](https://sdk.sphero.com/documentation/api-documents) that BOLT also uses |
| [edu.sphero.com](https://edu.sphero.com/) (Sphero Central) | All | Lessons, resources and an online program library (programs stored as `.lab` files) |
| `sphero.docsapp.io` | | The old Edu JavaScript/Python command docs. Not responding as of October 2026 |
| [sphero-inc/sphero-sdk-raspberrypi-python](https://github.com/sphero-inc/sphero-sdk-raspberrypi-python) | **RVR only** | Official Python SDK. Raspberry Pi talking to RVR over its UART port, not Bluetooth. asyncio and observer flavors; last updated 2024. |

Sphero's GitHub org exists but only covers RVR; there's no first-party
Python or JavaScript library for BOLT, Mini or SPRK+ over Bluetooth.

## Community libraries

| Library | Language | Status | Use it? |
|---|---|---|---|
| [spherov2.py](https://github.com/artificial-intelligence-class/spherov2.py) (`pip install spherov2`) | Python | v0.12.1, last commit Jan 2024. Reverse-engineered from the Edu app. BOLT, Mini, SPRK+, RVR, BB-8, R2-D2... | **Yes.** The recommended desktop library. |
| [igbopie/spherov2.js](https://github.com/igbopie/spherov2.js) | JavaScript (Node) | Last commit 2021. v2 protocol | For TypeScript/JS work, a starting point |
| [EnotYoyo/pysphero](https://github.com/EnotYoyo/pysphero) | Python | Earlier v2-protocol library that spherov2 credits as a reference | Prefer spherov2 |
| [orbotix/sphero.js](https://github.com/orbotix/sphero.js) | JavaScript | Last commit 2019. **v1 protocol** | Only for Sphero 2.0 / SPRK / Ollie |
| `sphero-bolt-plus` (PyPI, v1.0.1) | Python | **Does not work.** Sends JSON over a Nordic UART service; real robots use the binary v2 protocol on Sphero's own service. Its README links a placeholder repo. | **No** |

## How the pieces relate

```
Sphero Edu app ──(reverse engineered)──> spherov2.py ──> SpheroEduAPI (same command names)
       │                                      │
       └── both speak the v2 BLE protocol ────┘   (see protocol.md)
```

Because spherov2's `SpheroEduAPI` copies the Edu app's command names, code
moves between the two runtimes with small mechanical changes (see
[getting-started-desktop.md](getting-started-desktop.md)).
