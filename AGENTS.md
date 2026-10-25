# AGENTS.md

Guidance for AI coding assistants (and humans) working in this repo or
writing Sphero code for a user.

## First: which runtime is the code for?

There are two incompatible ways to run Python on a Sphero. Find out which one
the user has before writing code. A screenshot of a code editor with **Start**,
**AIM**, and tabs like *Movements / Lights / Matrix* at the bottom is the
**Sphero Edu app**.

### 1. Sphero Edu app (code pasted into the app's Python editor)

- **No imports.** Robot functions (`roll`, `set_speed`, `set_main_led`, ...)
  are globals provided by the app. Do not import `spherov2`, `math`, `sys`,
  `asyncio`, or anything else unless you know the app supports it. Do math
  by hand (`x ** 0.5`, `57.29578` for degrees per radian).
- **Entry point is `async def start_program():`**. The app calls it when the
  user presses Start. No `if __name__ == "__main__":`, no `asyncio.run`.
- **Calls that take time are awaited:** `await delay(s)`, `await roll(h, s, d)`,
  `await spin(a, d)`, `await speak(...)`, `await scroll_matrix_text(...)`.
  Instant setters are not: `set_speed`, `set_heading`, `stop_roll`,
  `set_main_led`, `set_back_led`, `set_matrix_pixel`.
- **Colors are dicts:** `{'r': 255, 'g': 0, 'b': 0}`.
- **Connection, aiming and stopping are handled by the app.** Don't write
  scanning, connect, or cleanup code. An infinite `while True:` loop is fine
  as long as it contains an `await` (otherwise the app freezes).
- Template: [`examples/edu_app/circles.py`](examples/edu_app/circles.py).

### 2. Desktop Python (script on a computer, Bluetooth to the robot)

- Use **[`spherov2`](https://pypi.org/project/spherov2/)** plus **`bleak`**:
  `pip install spherov2 bleak`. `spherov2` does not declare `bleak` as a
  dependency, so install it explicitly.
- Use the high-level `spherov2.sphero_edu.SpheroEduAPI`. It mirrors the Edu
  app's command names, but as **synchronous methods on `api`**
  (`api.set_speed(100)`, `api.roll(0, 100, 2)` blocks for 2 s) and colors
  are `spherov2.types.Color(r, g, b)`.
- Find a robot with `scanner.find_toy(toy_name="SB-1234", toy_types=[BOLT])`.
  BOLT names start with `SB-`.
- Template: [`examples/desktop/circles.py`](examples/desktop/circles.py).

## Libraries to avoid

- **`sphero-bolt-plus` (PyPI)**: does not work. Its source sends JSON over a
  Nordic UART service; Sphero robots use a binary protocol on a different
  service. Commands will time out. Recommend `spherov2` instead.
- **`orbotix/sphero.js`, `sphero` (npm)**: the old v1 protocol for Sphero
  2.0/SPRK/Ollie. Doesn't drive BOLT.
- **`sphero-sdk-raspberrypi-python`** is first-party and real, but **RVR
  only**, over a serial cable from a Raspberry Pi. Not for BOLT/Mini.

See [docs/ecosystem.md](docs/ecosystem.md).

## Driving facts that come up a lot

- Heading: degrees, 0 = the way the robot was aimed (blue tail light toward
  the user), 90 = right, 270 = left.
- Speed: 0-255, not a physical unit. Real speed depends on robot, floor and
  battery. BOLT at ~170 is roughly 1-1.3 m/s on a hard floor (rough, varies).
  For anything distance-based, read `get_velocity()` (cm/s) or
  `get_location()` / `get_distance()` (cm) instead of assuming.
- Circles: hold speed constant and advance heading at `v / r` rad/s, using
  measured velocity. `spin(360, t)` after `set_speed(...)` also makes a
  circle, but its size depends on the uncalibrated speed.
- Sharp high-speed turns slip. If a path comes out larger than asked, lower
  the speed before tweaking the math.

## Working in this repo

- Layout: `docs/` (guides and reference), `examples/edu_app/` (paste into the
  app), `examples/desktop/` (run with spherov2).
- Every example starts with a docstring or comment block saying which
  runtime it's for, which robot(s) it was tested on, and how to run it.
- Keep examples self-contained single files: users copy them one at a time.
- Edu-app examples must follow the runtime rules above (no imports, etc.).
- CI only checks that files compile; it can't reach a robot. Say clearly in
  your PR or reply whether code was **tested on hardware** or only
  **syntax-checked**. Don't claim hardware behaviour you didn't observe.
- When a fact comes from reverse-engineered or third-party sources rather
  than Sphero's docs, say so in the doc.

## Known unknowns (help wanted)

These are believed true but not yet confirmed against Sphero's current docs
or app. Verify before relying on them, and update this file when you do:

- Exactly which Edu-app Python calls are `await`ed.
- Whether the Edu app's Python allows any imports (`math`, `random`).
- BOLT+ Bluetooth name prefix and whether spherov2's `BOLT` class fully
  supports it.
- Any supported way to load code into the Edu app other than typing or
  pasting it (see [docs/edu-app-code-transfer.md](docs/edu-app-code-transfer.md)).
