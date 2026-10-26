#!/usr/bin/env python3
"""Drive a Sphero BOLT / BOLT+ in fast circles about 1 meter in diameter.

Runtime: desktop Python (spherov2)
Robot:   Sphero BOLT / BOLT+
Tested:  syntax-checked only

    pip install spherov2 bleak
    python circles.py              # first BOLT found
    python circles.py SB-1234      # a specific robot (BOLT+ names start BP-)

Before starting, aim the robot so its blue tail light faces you.
Press Ctrl+C to stop.

How it works: the robot drives at a fixed speed while we keep turning its
heading. For a circle of radius r, the turn rate has to be omega = v / r.
We read the robot's real speed from its wheel encoders (cm/s), so the circle
stays close to 1 m across even though the 0-255 speed setting doesn't map
exactly to a real-world speed.
"""

import math
import sys
import time

from spherov2 import scanner
from spherov2.sphero_edu import SpheroEduAPI
from spherov2.toy.bolt import BOLT
from spherov2.types import Color, ToyType


class BOLTPlus(BOLT):
    # spherov2 only recognizes BOLTs named SB-...; a BOLT+ advertises as BP-...
    toy_type = ToyType("Sphero BOLT+", "BP-", "BP", 0.075)



DIAMETER_CM = 100.0
SPEED = 170              # 0-255. Higher is faster but slips more on smooth floors.
EST_CM_PER_S = 120.0     # speed guess used until the encoders report a value
UPDATE_HZ = 25           # heading updates per second
CLOCKWISE = True

RADIUS_CM = DIAMETER_CM / 2


def measured_speed(api):
    """Return the robot's ground speed in cm/s, or None if there's no reading yet."""
    v = api.get_velocity()
    if not v or v.get("x") is None or v.get("y") is None:
        return None
    return math.hypot(v["x"], v["y"])


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else None
    print("Scanning for a BOLT..." if not name else f"Scanning for {name}...")
    toy = scanner.find_toy(toy_name=name, toy_types=[BOLT, BOLTPlus])
    print(f"Connecting to {toy.name}...")

    with SpheroEduAPI(toy) as api:
        api.set_main_led(Color(0, 120, 255))
        api.set_back_led(Color(0, 0, 255))
        api.set_stabilization(True)

        heading = 0.0
        speed_cm_s = EST_CM_PER_S
        direction = 1 if CLOCKWISE else -1
        dt_target = 1.0 / UPDATE_HZ

        api.set_heading(0)
        api.set_speed(SPEED)
        print(f"Driving circles about {DIAMETER_CM:.0f} cm across. Press Ctrl+C to stop.")

        last = time.monotonic()
        last_report = last
        try:
            while True:
                time.sleep(dt_target)
                now = time.monotonic()
                dt = now - last
                last = now

                # Smooth the measured speed so sensor noise doesn't make the turning jumpy.
                v = measured_speed(api)
                if v is not None and v > 10:
                    speed_cm_s = 0.8 * speed_cm_s + 0.2 * v

                # omega = v / r, converted to degrees per second.
                turn_rate_deg_s = math.degrees(speed_cm_s / RADIUS_CM)
                heading = (heading + direction * turn_rate_deg_s * dt) % 360
                api.set_heading(round(heading))

                if now - last_report > 2.0:
                    lap_s = 360.0 / turn_rate_deg_s
                    print(f"  speed {speed_cm_s:5.1f} cm/s, turn {turn_rate_deg_s:5.1f} deg/s, "
                          f"lap {lap_s:4.1f} s")
                    last_report = now
        except KeyboardInterrupt:
            print("\nStopping.")
        finally:
            api.stop_roll()
            api.set_main_led(Color(0, 0, 0))
            time.sleep(0.5)


if __name__ == "__main__":
    main()
