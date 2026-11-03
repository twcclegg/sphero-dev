"""Robot types spherov2 doesn't know about yet."""

from functools import partialmethod

from spherov2.controls import PacketDecodingException
from spherov2.controls.v2 import Packet, Processors
from spherov2.toy.bolt import BOLT
from spherov2.types import ToyType


class ResyncCollector:
    """Splits the robot's byte stream into packets, like spherov2's ``Collector``.

    spherov2's raises on a bad packet and drops the rest of that BLE chunk,
    which usually holds the start of the next packet, so one corrupted byte
    turns into a run of hundreds of bad packets (seen on a BOLT+ after a
    retried connection: 208 in 10 s, and the program drove blind). This one
    starts a new packet at every start byte (escaping keeps it out of packet
    bodies), skips bad packets, and counts them in ``errors``.
    """

    def __init__(self, callback):
        self._callback = callback
        self._data: list[int] = []
        self.errors = 0

    def add(self, data):
        for b in data:
            if b == Packet.Encoding.start:
                if self._data:
                    self.errors += 1  # previous packet never ended
                self._data = [b]
                continue
            if not self._data:
                continue  # between packets: noise
            self._data.append(b)
            if b == Packet.Encoding.end:
                pkt, self._data = self._data, []
                try:
                    packet = Packet.parse_response(pkt) if len(pkt) >= 6 else None
                except PacketDecodingException:
                    packet = None
                if packet is None:
                    self.errors += 1
                else:
                    self._callback(packet)


class _Packet(Packet):
    __slots__ = ()
    Collector = ResyncCollector


def decode_errors(toy) -> int:
    """Bad packets received so far (0 for toys without a ``ResyncCollector``)."""
    return getattr(getattr(toy, "_Toy__decoder", None), "errors", 0)


class BOLTPlus(BOLT):
    """Sphero BOLT+. Advertises as ``BP-XXXX``; spherov2 only matches ``SB-``.

    Speaks BOLT's commands, with two differences found on BP-5FBB (Oct 2026):

    - It has no anti-DoS service (``00020001-...``), so BOLT's
      ``usetheforce...band`` unlock fails with "Characteristic 00020005-...
      was not found". It needs no unlock.
    - Commands BOLT sends to its second processor (target ``0x12``: driving,
      sensors, the matrix, heading reset) come back with error 9, bad target
      ID. The same commands sent to processor 1 (``0x11``) are accepted, so
      every command goes there.

    It also uses :class:`ResyncCollector` to read packets.
    """

    toy_type = ToyType("Sphero BOLT+", "BP-", "BP", 0.075)
    _handshake = []
    _packet = _Packet


for _name, _method in vars(BOLT).items():
    if isinstance(_method, partialmethod) and _method.keywords.get("proc") == Processors.SECONDARY:
        setattr(BOLTPlus, _name, partialmethod(_method.func, *_method.args,
                                               **{**_method.keywords, "proc": Processors.PRIMARY}))
