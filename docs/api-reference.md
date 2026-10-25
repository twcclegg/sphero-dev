# Sphero Edu API reference

The Sphero Edu command set, grouped by topic. The same names work in both
runtimes:

- **Edu app**: call as globals, `await` the ones marked ⏱.
- **Desktop (spherov2)**: call as `api.name(...)`; ⏱ calls block until done.

Sources: Sphero's Edu docs (`sphero.docsapp.io`) as reproduced in the
spherov2 `SpheroEduAPI` docstrings. Robot columns show where a command
applies; anything not marked applies to all rolling robots.

## Movement

| Command | Notes |
|---|---|
| ⏱ `roll(heading, speed, duration)` | Heading 0-360°, speed -255..255, then stops |
| `set_speed(speed)` | -255..255, persists until changed |
| `set_heading(heading)` | Degrees. 0 = aimed direction, 90 right, 180 back, 270 left |
| `stop_roll(heading=None)` | Speed to 0 |
| ⏱ `spin(angle, duration)` | Degrees over seconds. With `set_speed` first, drives an arc |
| `raw_motor(left, right, duration)` | Direct motor power -255..255, bypasses heading control |
| `set_stabilization(on)` | Turn off to free-spin the shell (e.g. as a controller) |
| `reset_aim()` | Current direction becomes 0° |
| `calibrate_compass()` / `set_compass_direction(deg)` | BOLT only |

## Lights

| Command | Robots | Notes |
|---|---|---|
| `set_main_led(color)` | all | On BOLT, fills the whole 8x8 matrix |
| `set_back_led(color or brightness)` | all | Blue tail light on older robots |
| `set_front_led(color)` | BOLT, RVR | |
| ⏱ `fade(from, to, duration)` | all | |
| ⏱ `strobe(color, period, count)` | all | |

## BOLT LED matrix (8x8)

| Command | Notes |
|---|---|
| `set_matrix_pixel(x, y, color)` | x, y 0-7 |
| `set_matrix_line(x1, y1, x2, y2, color)` | |
| `set_matrix_fill(x1, y1, x2, y2, color)` | Filled box |
| `set_matrix_character(char, color)` | One character |
| ⏱ `scroll_matrix_text(text, color, fps, wait)` | |
| `set_matrix_rotation(rotation)` | |
| `clear_matrix()` | |
| `register_matrix_animation(...)`, `play_matrix_animation(id, loop)`, `pause_matrix_animation()`, `resume_matrix_animation()` | Frame animations |

## Sensors

| Command | Returns |
|---|---|
| `get_acceleration()` | `{x, y, z}` in g |
| `get_vertical_acceleration()` | g, -8..8 |
| `get_orientation()` | `{pitch, roll, yaw}` in degrees |
| `get_gyroscope()` | `{pitch, roll, yaw}` rotation rate, °/s |
| `get_velocity()` | `{x, y}` cm/s from the wheel encoders |
| `get_location()` | `{x, y}` cm from where the program started |
| `get_distance()` | Total cm travelled |
| `get_speed()` | The *target* speed you set, -255..255 (not measured) |
| `get_heading()` | The *target* heading |
| `get_luminosity()` | Lux (BOLT light sensor) |
| `get_compass_direction()` | BOLT, after calibration |

Sensor reads return the latest streamed value and may be `None` for the
first moments of a program.

## BOLT infrared (robot-to-robot)

`start_ir_broadcast(near, far)`, `start_ir_follow(near, far)`,
`start_ir_evade(near, far)`, their `stop_` counterparts, and
`send_ir_message(channel, intensity)`. Channels 0-7.

## Events

Event types: collision, freefall, landing, gyro max, charging, not charging,
IR message, color (RVR). In spherov2:

```python
from spherov2.sphero_edu import EventType

def on_hit(api):
    api.set_main_led(Color(255, 0, 0))

api.register_event(EventType.on_collision, on_hit)
```

In the Edu app the syntax differs; check Sphero's docs.

## Other robots

BB-8 / BB-9E / R2-D2 / R2-Q5 add `play_animation`, `play_sound`,
`set_dome_position`, `set_stance`, `set_waddle` and dome/holo-projector LEDs.
RVR adds side and headlight LEDs and a color sensor (`get_color`).
