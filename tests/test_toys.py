from functools import partialmethod

from spherov2.controls.v2 import Processors
from spherov2.toy.bolt import BOLT

from sphero_dev.toys import BOLTPlus


def test_boltplus_skips_the_unlock():
    assert BOLTPlus._handshake == []


def test_boltplus_sends_every_command_to_the_primary_processor():
    retargeted = [name for name, m in vars(BOLT).items() if isinstance(m, partialmethod)
                  and m.keywords.get("proc") == Processors.SECONDARY]
    assert "drive_with_heading" in retargeted
    for name in retargeted:
        assert vars(BOLTPlus)[name].keywords["proc"] == Processors.PRIMARY, name


def test_collector_recovers_after_a_bad_packet():
    from spherov2.controls.v2 import Packet

    from sphero_dev.toys import ResyncCollector

    good = bytes(Packet(Packet.Flags.is_response, 0x13, 0x0d, 1, None, None, bytearray(),
                        Packet.Error.success).build())
    got = []
    c = ResyncCollector(got.append)
    corrupt = good[:4] + bytes([good[4] ^ 0xFF]) + good[5:]
    # One chunk: a bad packet, then two good ones. spherov2's own collector
    # raises on the first and loses the rest of the chunk.
    c.add(corrupt + good + good[:3])
    c.add(good[3:] + good[:2])  # a truncated packet, cut off by the next start
    c.add(good)
    assert len(got) == 3 and c.errors == 2
