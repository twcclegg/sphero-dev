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
- **Confirmed on a BOLT+ (Oct 2026):** a program using only these ran in the
  app without errors: `async def start_program()`, `await delay(...)`,
  `set_speed`, `set_heading`, `get_velocity()`, `set_main_led({...})`,
  `set_back_led(255)`, a `while True:` loop, and plain helper functions.
- **Don't count on `delay` timing.** A circles program that turned by
  `rate * STEP` each `await delay(STEP)` drew circles far bigger than 1 m on
  a BOLT+. The likely cause (not yet measured) is that each loop takes longer
  than the delay; the simulator reproduces it with `--delay-overhead`. Steer
  from sensors instead (`get_location()`, `get_distance()`, `get_heading()`),
  as `examples/edu_app/circles.py` does.
- **Connection, aiming and stopping are handled by the app.** Don't write
  scanning, connect, or cleanup code. An infinite `while True:` loop is fine
  as long as it contains an `await` (otherwise the app freezes).
- Template: [`examples/edu_app/circles.py`](examples/edu_app/circles.py).
- The app saves programs as `.lab` files (JSON with the code inside).
  `sphero-dev export` / `import` convert between `.py` and `.lab`. To hand
  a user a program without copy/paste: export it, have them get the file
  onto the device and use the app's **Import** option (tested on iPad).
  Opening a `.lab` from the iPad Files app does not import it.
- **Check it before handing it over:** `sphero-dev run program.py --sim
  --seconds 20 --delay-overhead 0.1 --max-turn-rate 90` runs it in the
  simulator and prints where the robot went (`pip install -e .` in this
  repo). It catches crashes, missing `await`s that break a loop, and wrong
  geometry. Its physics are rough (see
  [docs/shim.md](docs/shim.md)), so it's not proof the robot will behave.

### 2. Desktop Python (script on a computer, Bluetooth to the robot)

- Use **[`spherov2`](https://pypi.org/project/spherov2/)** plus **`bleak`**:
  `pip install spherov2 bleak`. `spherov2` does not declare `bleak` as a
  dependency, so install it explicitly.
- Use the high-level `spherov2.sphero_edu.SpheroEduAPI`. It mirrors the Edu
  app's command names, but as **synchronous methods on `api`**
  (`api.set_speed(100)`, `api.roll(0, 100, 2)` blocks for 2 s) and colors
  are `spherov2.types.Color(r, g, b)`.
- Find a robot with `scanner.find_toy(toy_name="SB-1234", toy_types=[BOLT])`.
  BOLT names start with `SB-`. **BOLT+ names start with `BP-`** (seen on a
  real BOLT+), which spherov2 doesn't recognize at all, even by exact name.
  Add a `BOLTPlus` type (`sphero_dev.toys.BOLTPlus`, or the few lines in
  `examples/desktop/circles.py`) to `toy_types`. Whether every BOLT command
  works on a BOLT+ from spherov2 isn't tested yet.
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
- Circles: fix a center point, read `get_location()` each step, head along
  the circle (90° from the center-to-robot direction) with a correction for
  being off the radius. Turning at a fixed rate from timing (`v / r` times
  an assumed step) drifts in the Edu app. `spin(360, t)` after
  `set_speed(...)` also makes a circle, but its size depends on the
  uncalibrated speed.
- **Tight turns have a speed limit.** Steering from position at a fixed
  speed 170 on a BOLT+ drew wandering 1.5-2 m loops instead of 1 m. The
  simulator reproduces that with turning capped near 90°/s
  (`--max-turn-rate 90`); the real cap isn't measured. For tight paths,
  adapt speed to tracking error (slow down when drifting out), as
  `examples/edu_app/circles.py` does, rather than picking a fixed speed.
- The app's **Location chart** (shown after a run) plots `get_location()`
  over the run. Ask the user for a screenshot of it; it's the fastest way
  to see what a driving program really did.
- Sharp high-speed turns slip. If a path comes out larger than asked, lower
  the speed before tweaking the math.

## Working in this repo

- Layout: `docs/` (guides and reference), `examples/edu_app/` (paste into the
  app), `examples/desktop/` (run with spherov2), `src/sphero_dev/` (the shim
  and simulator), `tests/` (pytest, simulator only).
- Before pushing: `ruff check .` and `python -m pytest`. Every Edu-app
  example is run in the simulator by the tests.
- The shim's Edu globals live in `src/sphero_dev/edu.py`; the editor stubs in
  `src/sphero_dev/edu_builtins.pyi` (copied to
  `examples/edu_app/__builtins__.pyi`). Keep all three in sync with
  `docs/api-reference.md` when adding a command.
- Every example starts with a docstring or comment block saying which
  runtime it's for, which robot(s) it was tested on, and how to run it.
- Keep examples self-contained single files: users copy them one at a time.
- Edu-app examples must follow the runtime rules above (no imports, etc.).
- CI lints, runs the tests and simulates the examples; it can't reach a
  robot. Say clearly in your PR or reply whether code was **tested on
  hardware**, **simulated**, or only **syntax-checked**. Don't claim hardware
  behaviour you didn't observe.
- When a fact comes from reverse-engineered or third-party sources rather
  than Sphero's docs, say so in the doc.

## Known unknowns (help wanted)

These are believed true but not yet confirmed against Sphero's current docs
or app. Verify before relying on them, and update this file when you do:

- Exactly which Edu-app Python calls are `await`ed. Confirmed so far:
  `await delay(...)` works; `set_speed`, `set_heading`, `set_main_led`,
  `set_back_led`, `get_velocity` work without `await`.
- Whether the Edu app's Python allows any imports (`math`, `random`).
- Whether spherov2's BOLT commands fully work on a BOLT+ (name prefix is
  `BP-`, confirmed).
- How fast a BOLT/BOLT+ can actually turn at a given speed.
- Where the Edu app's Python command docs live now: `sphero.docsapp.io` no
  longer responds.
