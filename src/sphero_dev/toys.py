"""Robot types spherov2 doesn't know about yet."""

from spherov2.toy.bolt import BOLT
from spherov2.types import ToyType


class BOLTPlus(BOLT):
    """Sphero BOLT+. Advertises as ``BP-XXXX``; spherov2 only matches ``SB-``.

    Treated as a BOLT. That it speaks the same commands is an assumption,
    not yet tested on hardware from desktop Python.
    """

    toy_type = ToyType("Sphero BOLT+", "BP-", "BP", 0.075)
