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

## What's here

```
AGENTS.md                 Rules and context for AI coding assistants
docs/
  getting-started-edu-app.md
  getting-started-desktop.md
  api-reference.md        The Sphero Edu command set, grouped by topic
  ecosystem.md            Libraries that exist, which work, which to avoid
  protocol.md             How the Bluetooth protocol works under the hood
  edu-app-code-transfer.md  Research notes: getting code into the app without copy/paste
examples/
  edu_app/                Paste-into-the-app programs
  desktop/                Run-on-your-computer programs (spherov2)
```

## Roadmap

- More examples (LED matrix, sensors, collisions, IR follow on BOLT)
- Local "Edu app shim" so Edu-app programs can be linted, type-checked and
  run on desktop unchanged
- A way to send code to the Edu app without manual copy/paste (see
  [research notes](docs/edu-app-code-transfer.md))
- Possibly a PyPI package and TypeScript/JavaScript examples

## Contributing

Issues and PRs welcome. Please test on a real robot when you can and say
which robot and app/firmware version you used. See [AGENTS.md](AGENTS.md) for
conventions; they apply to humans too.

## Disclaimer

Not affiliated with or endorsed by Sphero, Inc. "Sphero", "BOLT" and related
names are trademarks of Sphero, Inc.
