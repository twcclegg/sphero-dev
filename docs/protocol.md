# The Sphero v2 Bluetooth protocol

You don't need this to write programs. It's here for people building
libraries (e.g. a TypeScript port) or debugging one.

Sources: Sphero's [API protocol page](https://sdk.sphero.com/documentation/api-documents)
(written for RVR, same packet format) and spherov2.py's implementation
(`spherov2/controls/v2.py`, `spherov2/toy/`). The BLE UUIDs and the unlock
string come from spherov2 only.

## BLE services

| UUID | Use |
|---|---|
| `00010002-574f-4f20-5370-6865726f2121` | API v2 characteristic (BOLT, Mini, SPRK+, ...): write commands, receive notifications |
| `00020005-574f-4f20-5370-6865726f2121` | Anti-DoS characteristic: write `usetheforce...band` after connecting to unlock the API |

(The `574f4f2053706865726f2121` suffix is ASCII `WOO Sphero!!`.)

Older v1 robots (Sphero 2.0, SPRK, Ollie) use `22bb746f-...` UUIDs and a
different packet format.

## Packet format

```
SOP  FLAGS  [TID]  [SID]  DID  CID  SEQ  [ERR]  DATA...  CHK  EOP
0x8D                                                           0xD8
```

| Field | Meaning |
|---|---|
| `SOP` / `EOP` | Start `0x8D` / end `0xD8` |
| `FLAGS` | bit0 is-response, bit1 requests-response, bit2 requests-only-error, bit3 is-activity, bit4 has-target-id, bit5 has-source-id |
| `TID`, `SID` | Target / source processor, present if flagged (RVR has two processors) |
| `DID`, `CID` | Device ID and command ID, e.g. drive is DID `0x16` (22) |
| `SEQ` | Sequence number, echoed in the response |
| `ERR` | Responses only. 0 success, 1 bad device, 2 bad command, 5 bad data length, 7 bad parameter, 8 busy... |
| `CHK` | `0xFF - (sum of bytes from FLAGS through DATA) & 0xFF` |

### Escaping

Inside the packet (everything between SOP and EOP), these bytes are escaped
with `0xAB` followed by a substitute:

| Byte | Escaped as |
|---|---|
| `0xAB` (escape) | `0xAB 0x23` |
| `0x8D` (start) | `0xAB 0x05` |
| `0xD8` (end) | `0xAB 0x50` |

All multi-byte values are big-endian. The checksum covers every byte
except SOP and EOP and is computed before escaping (per Sphero's page).
Each escaped value is the original with bit 0x88 cleared. spherov2 writes packets to the
characteristic in 20-byte chunks.

## Example: drive

`drive_with_heading` is DID `0x16`, CID `0x07`, data
`[speed, heading_hi, heading_lo, flags]` with heading big-endian and flags
`0x01` backward, `0x02` turbo, `0x04` fast turn, `0x20` enable drift.
See `spherov2/commands/drive.py` for the full drive command set.
