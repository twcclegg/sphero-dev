# Design notes: a Claude-powered app that drives the robot directly

**Status: proposal.** Nothing here is built yet beyond the pieces marked
*exists*. Protocol, BOLT+, iPad and licensing research is in
[direct-control-feasibility.md](direct-control-feasibility.md).

The idea: someone types *"drive a figure eight about a meter across, blue
while turning left and red while turning right"*. Claude writes the program,
the app checks it in the simulator, shows it, and on approval runs it on the
robot over Bluetooth. No Sphero Edu app and no copy/paste in between.

## The key fact: robots don't store programs

As far as the public v2 protocol shows, BOLT, Mini and SPRK+ don't run user
code onboard. The Sphero Edu app runs your program **on the phone/tablet/
computer** and streams individual commands (drive, set LED, read sensor) to
the robot over Bluetooth. So "push to the robot" really means "run the
program on a device that's connected to the robot". Whatever device hosts
the app also executes the program.

That's good news: anything that speaks the protocol can replace the Edu app,
and this repo already has a Python host.

## Pieces

| Piece | Status |
|---|---|
| Program format: Edu-app Python (`async def start_program()`) | *exists*. Keeps programs pasteable into the official app as a fallback |
| Rules and API reference to put in Claude's system prompt | *exists*: AGENTS.md (Edu section), [api-reference.md](api-reference.md) |
| Run a program on a robot from Python | *exists*: `sphero-dev run` ([shim.md](shim.md)) |
| Simulator to check a program before it moves a robot | *exists*: `SimBackend` |
| Claude API call that turns a request into a program | to build |
| UI (chat box, code view, Run / Stop) | to build |

## Generation loop

1. System prompt: the Edu-app rules from AGENTS.md plus api-reference.md.
   These are stable, so they can be prompt-cached.
2. Give Claude a `run_in_simulator(program)` tool that runs the program in
   `SimBackend` for N seconds and returns errors plus a path summary
   (distance, bounding box, final position). Claude can then check its own
   work ("is the figure eight about 100 cm wide?") and fix it before the
   user sees it.
3. Show the program and the simulated path. The user presses **Run**.
4. Run on the robot with a time limit and a big Stop button.

Minimal request, Python SDK (`pip install anthropic`):

```python
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    thinking={"type": "adaptive"},
    output_config={"effort": "medium"},
    betas=["server-side-fallback-2026-07-01"],
    fallbacks="default",
    system=SYSTEM_PROMPT,  # AGENTS.md Edu rules + docs/api-reference.md
    messages=[{"role": "user", "content": "Drive a figure eight about 1 m across"}],
)
if response.stop_reason == "refusal":
    raise RuntimeError("Request was declined")
program = "".join(b.text for b in response.content if b.type == "text")
```

`fallbacks="default"` retries on another model if a safety classifier
declines the request. In practice, add the simulator tool (step 2) and ask
for the program as structured output or a tool call so you don't have to
pull code out of prose.

## Where the app runs

| Option | Devices | Bluetooth | Effort | Notes |
|---|---|---|---|---|
| **A. Desktop Python app** (CLI or local web UI on `localhost`) | macOS, Windows, Linux, Raspberry Pi | `bleak` via spherov2 | Low. Mostly glue around what exists | Best first prototype |
| **B. Web app with Web Bluetooth** | Chrome/Edge on desktop, Android, Chromebook | Browser's Web Bluetooth API | Medium. Needs a TypeScript port of the protocol ([protocol.md](protocol.md), igbopie/spherov2.js as a start); run Python with Pyodide or have Claude write JS | **No iPad/iPhone Safari support.** Third-party iOS browsers with Web Bluetooth exist (e.g. Bluefy) |
| **C. Native iPad app** (Swift + CoreBluetooth) | iPad, iPhone | CoreBluetooth | High. Native app, protocol port, App Store review | The only option that serves iPad-only classrooms well |

A then B shares the most with what's here. C only if iPads are the main
audience.

## API keys and cost

- Never ship an Anthropic API key inside a browser or mobile app. For a
  personal desktop tool, read the user's own key from the environment.
  Anything distributed to others needs a small backend that holds the key,
  authenticates users, and rate-limits.
- Programs are short. One generation with a couple of simulator rounds is a
  handful of requests per program.

## Safety

- Always simulate first; refuse to run a program that errors or hangs.
- Cap speed (e.g. clamp `set_speed`/`roll` in the backend) and run time,
  and make Stop always reachable. Robots roll off tables.
- Ask before every run on hardware; don't let the model start a robot by
  itself.
- For classrooms, a teacher-facing setting for maximum speed.

## Open questions

- Does the Edu app's Python allow imports? If programs must stay pasteable
  into the app, generated code must avoid them.
- Sphero's terms for third-party apps: see the licensing section of
  [direct-control-feasibility.md](direct-control-feasibility.md).
- Protocol differences between BOLT+ and BOLT (the `BP-` name is confirmed).
