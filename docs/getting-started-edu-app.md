# Getting started in the Sphero Edu app

The Sphero Edu app (iPad, iPhone, Android, Chromebook, Windows, macOS) has
three ways to program: Draw, Blocks, and Text. Text programs can be written
in JavaScript or **Python**. The app handles Bluetooth, aiming, and starting
and stopping the program for you.

## Create a Python program

1. Open Sphero Edu, sign in, and connect your robot.
2. Create a new program and pick **Text**, then **Python**.
3. Delete the template code and paste in a program, e.g.
   [`examples/edu_app/circles.py`](../examples/edu_app/circles.py).
4. Tap **AIM** and rotate the robot so its blue tail light faces you.
5. Tap **Start**. Tap **Stop** to end.

## The shape of an Edu-app program

```python
async def start_program():
    set_main_led({'r': 0, 'g': 0, 'b': 255})
    await roll(0, 100, 2)      # heading 0°, speed 100, for 2 seconds
    await spin(360, 1)         # one full turn over 1 second
    set_speed(80)
    await delay(1.5)
    stop_roll()
```

Rules that trip people up:

- **No imports.** All robot commands are already defined. Code written for
  desktop Python (`from spherov2 import ...`, `import sys`) shows dozens of
  errors in the Problems panel.
- **`start_program` is the entry point** and must be `async`.
- **Anything that takes time needs `await`**: `delay`, `roll`, `spin`,
  `speak`, scrolling text.
- **Never write a tight loop without an `await`** inside it. The program
  can't update the robot or respond to Stop.
- Colors are `{'r': ..., 'g': ..., 'b': ...}` with values 0-255.

## Useful commands

See [api-reference.md](api-reference.md) for the full list. The most used:

| Command | What it does |
|---|---|
| `await roll(heading, speed, seconds)` | Drive, then stop |
| `set_speed(speed)` / `set_heading(deg)` | Change speed or direction and keep going |
| `stop_roll()` | Stop |
| `await spin(degrees, seconds)` | Turn in place (or in an arc if moving) |
| `await delay(seconds)` | Wait |
| `set_main_led(color)` | Whole BOLT matrix one color |
| `set_matrix_pixel(x, y, color)` | One pixel on BOLT's 8x8 matrix |
| `get_velocity()` | `{'x', 'y'}` in cm/s |
| `get_location()` | `{'x', 'y'}` in cm from the start point |
| `get_heading()` | Current heading in degrees |

## Events

Edu programs can react to events such as collisions by defining an async
function and registering it. See Sphero's docs for the exact syntax in
Python; it hasn't been verified for this repo yet.

## Moving code from your computer into the app

Either copy and paste the code into the editor, or import it as a file:

1. On the computer: `sphero-dev export program.py --name "My Program"`
   (see [shim.md](shim.md)). This writes `program.lab`, the app's own
   program format.
2. Get the file onto the tablet (AirDrop, Files, iCloud Drive).
3. In the Edu app, use **Import** and pick the file.

Opening the file from the iPad Files app launches Sphero Edu but doesn't
import it; use the app's Import instead. Details in
[edu-app-code-transfer.md](edu-app-code-transfer.md).
