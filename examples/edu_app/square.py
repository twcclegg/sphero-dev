# Runtime: Sphero Edu app (paste into a new Python program), or
#          sphero-dev run square.py --robot BP-XXXX
# Robot:   Sphero BOLT / BOLT+
# Tested:  run on a BOLT+ with sphero-dev run (hardwood, Oct 2026): corners
#          measured at (0, 33), (28, 29), (29, -1), back within 2 cm of the
#          start in 7.7 s. Not yet run in the Edu app.
#
# Drives a 30 cm square (forward, right, back, left) and ends at the start.
# Written by sphero-dev ask (Claude), kept as the pattern for "drive to a
# point": drive continuously with set_heading/set_speed, steer back onto
# the line, stop early by speed x coast time, and give every leg a time
# limit so a blocked robot moves on.

GREEN = {'r': 0, 'g': 255, 'b': 0}
SIDE = 30
SPEED = 50
COAST_TIME = 0.45  # s of travel after the stop command

# (heading, unit x, unit y, target x, target y)
LEGS = [
    (0, 0, 1, 0, SIDE),
    (90, 1, 0, SIDE, SIDE),
    (180, 0, -1, SIDE, 0),
    (270, -1, 0, 0, 0),
]


async def drive_leg(heading, ux, uy, tx, ty):
    set_heading(heading)
    set_speed(SPEED)
    last = heading
    for _ in range(80):  # time limit, ~8 s or more
        await delay(0.1)
        loc = get_location()
        if loc is None:
            continue
        dx = tx - loc['x']
        dy = ty - loc['y']
        remaining = dx * ux + dy * uy
        vel = get_velocity()
        va = 0
        if vel is not None:
            va = vel['x'] * ux + vel['y'] * uy
        if va < 0:
            va = 0
        if remaining <= 1 + va * COAST_TIME:
            break
        cross = dx * uy - dy * ux  # + means the line is to the right
        if cross > 10:
            cross = 10
        if cross < -10:
            cross = -10
        want = (heading + int(cross * 1.5)) % 360
        if abs(want - last) >= 4:  # each command costs ~0.1 s; skip tiny changes
            set_heading(want)
            last = want
    stop_roll()
    await delay(0.6)


async def start_program():
    set_main_led(GREEN)
    for leg in LEGS:
        await drive_leg(leg[0], leg[1], leg[2], leg[3], leg[4])
    stop_roll()
