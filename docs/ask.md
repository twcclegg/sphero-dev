# `sphero-dev ask`: describe it, Claude writes it, the robot runs it

**Status, Oct 2026:** run end to end on a BOLT+ (BP-5FBB) from Linux:
Claude (Sonnet, through a Claude subscription) wrote square, triangle and
figure-eight programs, and the 30 cm square ran on the robot as simulated
(corners within a few cm, back within 2 cm of the start, 7.7 s against 7.9 s
simulated). The conversation loop is also tested against scripted fakes of
the API and of `claude -p`.

```text
$ sphero-dev ask "drive a figure eight about a meter long, blue on the left loop, red on the right" --robot BP-5FBB
Asking Claude...
  simulating 20 s...
  checking the final program...
------------------------------------------------------------------------
Figure eight
------------------------------------------------------------------------
# Drives a figure eight ...
async def start_program():
    ...
------------------------------------------------------------------------
Two 50 cm loops steered from get_location(), speed capped at 150 ...

Simulator (rough; no slipping or collisions):
  Ran the full 30 s without errors.
  Travelled 1490 cm. Ended at (3, -2) cm. Path spans x -51..52, y -26..27 cm. ...
[r]un on robot, [s]ave, [q]uit, or type a change:
```

(Illustrative output, not a real run.)

At the prompt:
- **r** connects over Bluetooth and runs the program on the robot.
- **s** saves `figure_eight.py`, plus a `.lab` you can import into the Edu app.
- **q** quits.
- **Anything else** goes back to Claude as a change request. After a run,
  your text is sent as "I ran it on the real robot. …". So "it drifted
  right and the loops were too big" is a good reply.

## Setup

Linux (tested on Ubuntu-family distros such as Mint, via BlueZ) and macOS.
Python 3.10+.

```bash
git clone https://github.com/twcclegg/sphero-dev && cd sphero-dev
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[ai]'
sphero-dev ask "drive a square, 50 cm a side"
```

**Which Claude account pays.** If the [Claude Code](https://claude.com/claude-code)
CLI (`claude`) is installed and logged in, `ask` uses it (`claude -p`), and
the requests count against that Claude subscription. `ANTHROPIC_API_KEY` is
removed from its environment so it can't bill an API key by mistake.
Otherwise, or with `--via api`, it calls the API with `ANTHROPIC_API_KEY`
(from console.anthropic.com) and needs `pip install -e '.[ai]'`.

- **Linux:** needs BlueZ, which Mint ships with Bluetooth turned on. No
  root needed.
- **macOS:** the first scan asks to let your terminal app use Bluetooth.
  Allow it, under System Settings → Privacy & Security → Bluetooth.
- **Docker:** fine on Linux with `--net=host` and the D-Bus socket mounted.
  It **can't reach Bluetooth on macOS**, because Docker Desktop runs a VM.
  Run natively there.
- **Turn the robot on, and close the Edu app** (or turn off Bluetooth on the
  iPad). A robot accepts one connection at a time.

## Options

| Flag | Default | |
|---|---|---|
| `--robot NAME` | first robot found | e.g. `BP-5FBB` (BOLT+ names start `BP-`, BOLT `SB-`) |
| `--seconds N` | 30 | every run on the robot stops after this |
| `--max-speed N` | 150 | hard cap, 0-255, enforced by the backend whatever the program asks; Claude is told about it too |
| `--model` | `claude-sonnet-5-5` | `claude-haiku-5-5` is faster and cheaper |
| `--via` | `auto` | `claude-code` (subscription, through `claude -p`), `api` (`ANTHROPIC_API_KEY`), or `auto`: `claude-code` when `claude` is on PATH |
| `--effort` | medium | Claude's reasoning effort: `low` is faster and cheaper, `high` is for tricky paths |
| `-o DIR` | `.` | where **s** saves |

## How it works

1. Your request goes to Claude (`claude-sonnet-5-5` by default). The
   system prompt holds:
   - the Edu-app dialect rules and measured BOLT+ facts from
     [AGENTS.md](../AGENTS.md);
   - the command stubs (`edu_builtins.pyi`);
   - [api-reference.md](api-reference.md).
2. Claude has two tools.
   - **`simulate`** runs a draft in the simulator, with the settings that
     match a real BOLT+: a 0.1 s loop overhead and a 0.2 s heading lag. It
     reports errors, printed output, commands sent, and the path once a
     second. Claude reads the path and fixes its own geometry.
   - **`propose_program`** submits the final program. It's simulated again
     and sent back to Claude if it crashes or hangs, or if it breaks the
     dialect (imports, no `start_program`).
3. You see the program and decide. Nothing moves until you press **r**.

Simulation runs in a separate process, so a loop with no `await` times out
instead of freezing the CLI. Programs stay in the Edu-app dialect, so
anything it writes also pastes into the app.

## Safety

- Nothing runs on the robot without you choosing **r**.
- Speed is capped in the backend (`--max-speed`), not only by asking Claude.
- Each run stops after `--seconds`, and Ctrl-C stops the robot at once.
- While a program runs, a watchdog checks the robot's data. If packets
  arrive garbled or sensor samples stop for a second, it stops the robot
  and ends the program, rather than let it drive blind. (This happened
  once, after a retried connection: the location read (0, 0) while the
  robot drove into furniture.)
- After a run you see what the robot's sensors measured: time, distance,
  where it ended, and when it seemed stuck. If you type a change, Claude
  gets the measured path too.
- Clear the floor. Location comes from the wheels, so bumps and soft
  surfaces (a bed, thick carpet) make it wrong.
- Programs run as ordinary Python on your computer, with the shim's globals.
  The dialect check blocks imports, but this is **not a sandbox**. Read what
  you're about to run, as you would any code.

## Cost

Each request is one conversation: a few API calls, each with a roughly 10k
token system prompt (cached after the first call) plus a few simulator
round trips. See Anthropic's pricing page for current rates.
