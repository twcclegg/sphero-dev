# Runtime: Sphero Edu app (paste into a new Python program)
# Robot:   Sphero BOLT / BOLT+
# Tested:  simulated. An earlier timing-based version ran on a BOLT+ in the
#          app (no errors) but drew circles far bigger than 1 m.
#
# Drives fast circles about 1 meter across.
# Aim the robot (AIM button) so the blue tail light faces you, then press Start.
# Press Stop to end.
#
# The circle's center is fixed 50 cm to the robot's right (left if
# CLOCKWISE is False) of where it starts. Each step we read the robot's
# position, point it along the circle (a little ahead), and steer back in if
# it has drifted off. Steering from position means the size doesn't depend
# on how fast the loop runs or how fast the robot really goes.

DIAMETER_CM = 100.0
SPEED = 170          # 0-255. Lower it if the robot slips and the circle smears.
GAIN = 1.0           # degrees of extra turn per cm off the circle
MAX_CORRECTION = 45  # degrees
STEP_S = 0.04        # seconds between steering updates
CLOCKWISE = True

RADIUS_CM = DIAMETER_CM / 2
DEG_PER_RAD = 57.29578


def angle_deg(x, y):
    """Direction of (x, y) in Sphero heading degrees: 0 = forward (+y), 90 = right (+x).

    Same as atan2(x, y) in degrees; written out because the app has no math module.
    """
    ax, ay = abs(x), abs(y)
    if ax == 0 and ay == 0:
        return 0.0
    if ay >= ax:
        z = ax / ay
        a = 0.7853982 * z - z * (z - 1) * (0.2447 + 0.0663 * z)  # atan(z), radians
    else:
        z = ay / ax
        a = 1.5707963 - (0.7853982 * z - z * (z - 1) * (0.2447 + 0.0663 * z))
    a = a * DEG_PER_RAD
    if y < 0:
        a = 180 - a
    if x < 0:
        a = -a
    return a


async def start_program():
    set_main_led({'r': 0, 'g': 120, 'b': 255})
    set_back_led(255)

    direction = 1 if CLOCKWISE else -1
    center_x = direction * RADIUS_CM
    center_y = 0.0

    set_heading(0)
    set_speed(SPEED)
    last_distance = 0.0

    while True:
        await delay(STEP_S)

        loc = get_location()
        if not loc:
            continue

        dx = loc['x'] - center_x
        dy = loc['y'] - center_y
        off_by = (dx * dx + dy * dy) ** 0.5 - RADIUS_CM  # + means outside

        # Between updates the robot drives straight, cutting outside the
        # circle. Aim ahead by half the arc it covered last step to cancel that.
        travelled = get_distance() or 0.0
        step_cm = travelled - last_distance
        last_distance = travelled
        lead = step_cm / RADIUS_CM * DEG_PER_RAD / 2
        if lead > 30:  # guard against a jump in the first distance reading
            lead = 30

        correction = GAIN * off_by
        if correction > MAX_CORRECTION:
            correction = MAX_CORRECTION
        if correction < -MAX_CORRECTION:
            correction = -MAX_CORRECTION

        # Along the circle is 90 degrees from the center-to-robot direction;
        # the correction turns toward the center when outside, away when inside.
        heading = angle_deg(dx, dy) + direction * (90 + correction + lead)
        set_heading(int(heading) % 360)
