# Running Edu-app programs outside the app

`sphero-dev` runs a program written for the Sphero Edu app's Python editor,
**unchanged**, either on a real robot from your computer or in a simulator.
The same file can still be pasted into the app.

```bash
pip install -e .            # from a clone of this repo (not on PyPI yet)

sphero-dev run examples/edu_app/circles.py --sim                # simulator, 30 s
sphero-dev run examples/edu_app/circles.py --sim --seconds 20 --trace path.csv
sphero-dev run examples/edu_app/circles.py                      # first robot found
sphero-dev run examples/edu_app/circles.py --robot SB-1234 --seconds 60
```

`run` also accepts `.lab` files exported from the Edu app. To move programs
between this repo and the app:

```bash
sphero-dev export examples/edu_app/circles.py --name "Circles"   # -> circles.lab
sphero-dev import "Untitled Program.lab" -o program.py
```

Ctrl+C stops a robot run. Aim the robot first so its blue tail light faces
you; 0° is wherever it's pointing when the program starts.

## How it works

The shim builds the globals an Edu program expects (`roll`, `set_speed`,
`delay`, `set_main_led`, ...), runs the file's top level with them, then
awaits `start_program()`. Each call goes to a backend:

- **`RobotBackend`** forwards to spherov2's `SpheroEduAPI` over Bluetooth.
  `delay` is a real `asyncio.sleep`; event handlers registered with
  `register_event` are called when spherov2 reports the event.
- **`SimBackend`** is a 2D model with a virtual clock. `delay(5)` advances
  simulated time instantly, so a long program finishes in milliseconds.
  It records the path in `trace`.

The Edu app's `{'r': ..., 'g': ..., 'b': ...}` colors are converted for
spherov2. `roll`, `spin`, `fade` and `strobe` are implemented in the shim on
top of `set_heading` / `set_speed` / `set_main_led`, so they behave the same
on both backends.

## What the simulator is (and isn't)

It checks program **logic**: that it runs, that it doesn't crash or hang,
and roughly where the robot goes. Its physics are assumptions, not
measurements:

- ground speed = 0.7 cm/s per speed unit, reached with a 0.25 s time constant
- the robot turns to any heading instantly and never slips, unless you pass
  `--max-turn-rate DEG_S`. A BOLT+ that couldn't hold a 1 m circle at speed
  170 matched the simulator with about 90°/s, so try `--max-turn-rate 90`
  for anything with tight turns
- lights, matrix, IR and sound are accepted and ignored; events never fire
- `delay(s)` takes exactly `s` unless you pass `--delay-overhead`. On a real
  BOLT+ in the Edu app, a program that assumed `await delay(0.04)` took
  exactly 0.04 s drew circles far bigger than 1 m. A slower-than-asked loop
  is the likely cause (not yet measured), and `--delay-overhead 0.1`
  reproduces it here, so test anything timing-based with it.

Real robots slip on tight fast turns, vary with floor and battery, and
report `None` from sensors for the first moments. Calibrate `cm_per_unit`
against your robot if you need closer numbers.

## Editor support

Edu programs use globals that don't exist in normal Python, so editors flag
every robot call. Write a stub file the editor understands:

```bash
sphero-dev stubs examples/edu_app      # writes examples/edu_app/__builtins__.pyi
```

Pyright / Pylance (VS Code) then know every command, its arguments, and
which ones must be awaited. This repo already has one in
`examples/edu_app/`.

## Using it from Python

```python
import asyncio
from sphero_dev import SimBackend, run_program

sim = SimBackend()
asyncio.run(run_program("examples/edu_app/circles.py", sim, seconds=20))
print(sim.x, sim.y, sim.distance, len(sim.trace))
```

## Limits

- The shim's split between awaited and instant calls is our understanding
  of the app, not yet confirmed against Sphero's docs. If the app rejects
  something the shim accepts (or the other way round), the app wins; please
  open an issue.
- Only the commands in [api-reference.md](api-reference.md) are provided.
  `speak` prints instead of speaking.
- Event handler signatures in the Edu app aren't confirmed. The shim calls
  a handler with as many arguments as it declares (usually none).
