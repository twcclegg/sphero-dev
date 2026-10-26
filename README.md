# sphero-dev

A starting point for writing Python programs for Sphero robots, for people
and for AI coding assistants.

Sphero publishes docs at [sdk.sphero.com](https://sdk.sphero.com/documentation/sdk-documents)
and an Edu app with a built-in Python editor, but there's no single place on
GitHub that explains how the pieces fit together. This repo collects that
knowledge, working examples, and an [AGENTS.md](AGENTS.md) so AI assistants
write code that runs the first time.

> Status: early. Examples target **Sphero BOLT / BOLT+**. Other robots
> (Mini, SPRK+, RVR, BB-8, R2-D2) mostly share the same API.

## Two ways to run Python on a Sphero

These look alike but are **not interchangeable**. Pick one before you write
code.

| | Sphero Edu app | Desktop Python |
|---|---|---|
| Where code runs | Inside the Sphero Edu app (iPad, phone, Chromebook, desktop) | Your computer, talking to the robot over Bluetooth |
| Library | Built into the app, no imports | [`spherov2`](https://github.com/artificial-intelligence-class/spherov2.py) (unofficial, MIT) |
| Entry point | `async def start_program():` | Normal script, `with SpheroEduAPI(toy) as api:` |
| Calls look like | `set_speed(100)`, `await delay(1)` | `api.set_speed(100)`, `time.sleep(1)` |
| Good for | Classrooms, quick experiments, no setup | Real Python: files, git, libraries, tests, AI agents |

Guides:

- [Getting started in the Sphero Edu app](docs/getting-started-edu-app.md)
- [Getting started with desktop Python](docs/getting-started-desktop.md)

## Quick start (desktop)

```bash
pip install spherov2 bleak
python examples/desktop/circles.py
```

Aim the robot so its blue tail light faces you, then run. Ctrl+C stops it.

## Quick start (Edu app)

Create a new **Python** program in the Sphero Edu app, delete the template,
paste in [`examples/edu_app/circles.py`](examples/edu_app/circles.py), and
press **Start**.

## Run Edu-app programs from your computer

`sphero-dev` runs a program written for the Edu app, unchanged, on a robot
over Bluetooth or in a simulator. The simulator lets you (or an AI assistant)
check a program without a robot.

```bash
pip install -e .        # from a clone; not on PyPI yet
sphero-dev run examples/edu_app/circles.py --sim --seconds 20
# Simulated 20.0 s: travelled 2351 cm, ended at (104, 2) cm, path spans 105 x 101 cm
sphero-dev run examples/edu_app/circles.py --robot SB-1234
sphero-dev export examples/edu_app/circles.py   # -> circles.lab; import it in the Edu app
```

See [docs/shim.md](docs/shim.md).

## Ask Claude to write and run a program

```bash
pip install -e '.[ai]' && export ANTHROPIC_API_KEY=...
sphero-dev ask "drive a square, 50 cm a side, green on each corner" --robot BP-5FBB
```

Claude writes an Edu-app program and checks it in the simulator, and you
choose whether to run it, save it (`.py` and `.lab`), or describe a change.
Linux and macOS. See [docs/ask.md](docs/ask.md).

## What's here

```
AGENTS.md                 Rules and context for AI coding assistants
src/sphero_dev/           The shim: run Edu-app programs on a robot or simulator
tests/                    Simulator tests (no robot needed)
docs/
  getting-started-edu-app.md
  getting-started-desktop.md
  api-reference.md        The Sphero Edu command set, grouped by topic
  ecosystem.md            Libraries that exist, which work, which to avoid
  protocol.md             How the Bluetooth protocol works under the hood
  shim.md                 Running Edu-app programs outside the app
  ask.md                  sphero-dev ask: Claude writes the program, you run it
  edu-app-code-transfer.md  Research notes: getting code into the app without copy/paste
  direct-to-robot-app.md  Design notes: a Claude-powered app that drives the robot directly
  direct-control-feasibility.md  Is the Bluetooth protocol known? BOLT+, iPad, licensing
examples/
  edu_app/                Paste-into-the-app programs
  desktop/                Run-on-your-computer programs (spherov2)
```

## Roadmap

- More examples (LED matrix, sensors, collisions, IR follow on BOLT)
- Confirm the shim's behaviour against the real Edu app and Sphero's docs
- A way to send code to the Edu app without manual copy/paste (see
  [research notes](docs/edu-app-code-transfer.md))
- Try `sphero-dev ask` against the real API and a BOLT+, then grow it
  (see [design notes](docs/direct-to-robot-app.md))
- Publish `sphero-dev` to PyPI; TypeScript/JavaScript later

## Contributing

Issues and PRs welcome. Please test on a real robot when you can and say
which robot and app/firmware version you used. See [AGENTS.md](AGENTS.md) for
conventions; they apply to humans too.

## Disclaimer

Not affiliated with or endorsed by Sphero, Inc. "Sphero", "BOLT" and related
names are trademarks of Sphero, Inc.
