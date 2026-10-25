# Getting started with desktop Python

Run Python on your computer and control the robot over Bluetooth Low Energy.
This uses [`spherov2`](https://github.com/artificial-intelligence-class/spherov2.py),
an unofficial MIT-licensed library built by reverse-engineering the Sphero Edu
app. It's used in UPenn's CIS 521 course.

## Requirements

- Python 3.9+ (spherov2 says 3.7+; modern `bleak` needs newer)
- A computer with Bluetooth LE (macOS, Windows 10+, Linux with BlueZ)
- A charged robot that is **not** connected to the Edu app or another device
  (a robot accepts one Bluetooth connection at a time)

## Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install spherov2 bleak
```

`bleak` must be installed separately; spherov2 doesn't list it as a
dependency.

## First program

```python
from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.types import Color

toy = scanner.find_toy()                  # first Sphero found
with SpheroEduAPI(toy) as api:
    api.set_main_led(Color(0, 0, 255))
    api.roll(0, 100, 2)                   # heading, speed, seconds (blocks)
    api.spin(360, 1)
```

`SpheroEduAPI` uses the same command names as the Edu app, but:

| Edu app | spherov2 |
|---|---|
| `await roll(0, 100, 2)` | `api.roll(0, 100, 2)` |
| `await delay(1)` | `time.sleep(1)` |
| `{'r': 255, 'g': 0, 'b': 0}` | `Color(255, 0, 0)` |
| Connects for you | `scanner.find_toy()` + `with SpheroEduAPI(toy)` |

On entry the `with` block wakes the robot and starts sensor streaming; on
exit it puts the robot to sleep.

## Picking a specific robot

```python
from spherov2.toy.bolt import BOLT
toy = scanner.find_toy(toy_name="SB-1234", toy_types=[BOLT])
```

The robot's name is shown on the Edu app's connect screen (BOLT names start
with `SB-`). `scanner.find_toys()` lists everything
nearby.

## Troubleshooting

- **`ToyNotFoundError`**: the robot is asleep (put it on the charger briefly
  or tap it), out of range, or still connected to the Edu app.
- **macOS**: your terminal app needs Bluetooth permission (System Settings ›
  Privacy & Security › Bluetooth).
- **Linux**: BlueZ must be running; you may need to be in the `bluetooth`
  group.
- **Robot drifts off the expected direction**: aim it before running so the
  blue tail light faces you; 0° is wherever it's facing when the program
  starts.

## Running a robot from another machine

spherov2 has a TCP relay so the Bluetooth radio can live on a different
computer (e.g. a Raspberry Pi near the robot):

```bash
# on the machine with Bluetooth
python -m spherov2.adapter.tcp_server 0.0.0.0 50004
```

```python
from spherov2.adapter.tcp_adapter import get_tcp_adapter
toy = scanner.find_toy(adapter=get_tcp_adapter("pi.local"))
```
