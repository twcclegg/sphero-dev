# Runtime: Sphero Edu app (paste into a new Python program)
# Robot:   Sphero BOLT / BOLT+
# Tested:  syntax-checked only
#
# Drives fast circles about 1 meter across.
# Aim the robot (AIM button) so the blue tail light faces you, then press Start.
# Press Stop to end.
#
# The robot drives at a fixed speed while we keep turning its heading.
# For a circle of radius r the turn rate must be v / r, so we read the real
# speed from the wheel encoders to keep the circle close to 1 m.

DIAMETER_CM = 100.0
SPEED = 170              # 0-255. Higher is faster but slips more on smooth floors.
EST_CM_PER_S = 120.0     # speed guess used until the encoders report a value
STEP_S = 0.04            # seconds between heading updates
CLOCKWISE = True

RADIUS_CM = DIAMETER_CM / 2
DEG_PER_RAD = 57.29578


def measured_speed():
    v = get_velocity()
    if not v:
        return None
    return (v['x'] ** 2 + v['y'] ** 2) ** 0.5


async def start_program():
    set_main_led({'r': 0, 'g': 120, 'b': 255})
    set_back_led(255)

    heading = 0.0
    speed_cm_s = EST_CM_PER_S
    direction = 1 if CLOCKWISE else -1

    set_heading(0)
    set_speed(SPEED)

    while True:
        await delay(STEP_S)

        # Smooth the measured speed so sensor noise doesn't make turning jumpy.
        v = measured_speed()
        if v is not None and v > 10:
            speed_cm_s = 0.8 * speed_cm_s + 0.2 * v

        # Turn rate = v / r, in degrees per second.
        turn_rate = speed_cm_s / RADIUS_CM * DEG_PER_RAD
        heading = (heading + direction * turn_rate * STEP_S) % 360
        set_heading(int(heading))
