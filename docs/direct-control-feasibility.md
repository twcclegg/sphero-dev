# Feasibility: controlling a BOLT / BOLT+ without the Sphero Edu app

**Status: research, Oct 2026.** Nothing here has been tested on a BOLT+ yet
unless it says so. Companion to [direct-to-robot-app.md](direct-to-robot-app.md),
which covers the app design.

## Short answer

Feasible. Most of the protocol is already known, so there's little to
decipher.

| Layer | Public? | Source |
|---|---|---|
| Packet framing (SOP/EOP, flags, escaping, checksum, error codes) | **Yes, first-party** | Sphero's API docs at sdk.sphero.com, written for RVR. Same framing as BOLT ([protocol.md](protocol.md)) |
| BLE service / characteristic UUIDs, the `usetheforce...band` unlock | No | Community reverse engineering (spherov2, pysphero, spherov2.js) |
| BOLT command set: drive, LEDs, 8x8 matrix, sensor streaming, locator, power | No, but already decoded | Same libraries. spherov2 says its code was worked out from the decompiled Sphero Edu **Android** app |
| BOLT+ differences (`BP-` name, 128x128 LCD) | No, and nothing found | Nobody has published anything on BOLT+ specifically. The name prefix is confirmed on the user's robot |
| Firmware | No | Delivered by the app, almost certainly signed. Not needed |

The libraries are all MIT licensed:
- [spherov2.py](https://github.com/artificial-intelligence-class/spherov2.py) is used by this repo;
- [spherov2.js](https://github.com/igbopie/spherov2.js) is Node, last released in 2022;
- [pysphero](https://github.com/EnotYoyo/pysphero) is the other Python library.

Our own evidence on the BOLT+ is that Edu-app programs written for BOLT ran
on it unchanged. The app's command set, at least, is shared. That suggests
the wire protocol is mostly shared too, but **it doesn't prove it**.

## The unknowns, and the cheapest way to settle each

1. **Does spherov2 drive a BOLT+?** This is a one-evening test from a
   laptop with Bluetooth: `sphero-dev run examples/edu_app/circles.py
   --robot BP-5FBB`. That command already includes the `BOLTPlus` type. The
   checklist below covers the rest. This one test decides most of the plan.
2. **Anything that doesn't work** (most likely the LCD, maybe sensor
   streaming): capture the Edu app talking to the robot and compare it with
   spherov2's packets. See "Capturing traffic" below.
3. **LCD commands.** These are BOLT+ only and unknown. On the BOLT, the 8x8
   matrix is IO device `0x1A`. The LCD may reuse those commands, or have
   new ones that only a capture will show.

### BOLT+ test checklist

| Feature | spherov2 call | Result |
|---|---|---|
| Find and connect | `find_toy(toy_name="BP-…", toy_types=[BOLTPlus])` | untested |
| Drive and heading | `api.roll`, `api.set_heading` | untested |
| Main and back LEDs | `api.set_main_led`, `api.set_back_led` | untested |
| Location, velocity, heading streaming | `api.get_location()`, `get_velocity()` | untested |
| Matrix / LCD | `api.set_matrix_character`, `set_matrix_pixel` | untested; LCD expected to differ |
| Battery | `Power.get_battery_voltage` | untested |
| Collision event | `api.register_event(EventType.on_collision, …)` | untested |

## Capturing traffic

You only need this for features spherov2 gets wrong on a BOLT+. Ways to do
it, easiest first:

| Method | Hardware | Notes |
|---|---|---|
| **iPad + Mac PacketLogger** | Mac, cable | Install Apple's *Bluetooth logging profile* on the iPad (from developer.apple.com/bug-reporting/profiles-and-logs). PacketLogger, in Xcode's Additional Tools, then records the iPad's Bluetooth traffic live. This captures the app you already use, on the device you already have |
| **Android HCI snoop log** | Android phone | Developer options, then *Enable Bluetooth HCI snoop log*. Run the Edu app, take a bug report, and open `btsnoop_hci.log` in Wireshark |
| **nRF52840 sniffer dongle** | about $10–40 dongle | Nordic's free sniffer plugin for Wireshark. Works with any phone, but you have to follow the connection, so it's fussier |

Wireshark decodes the BLE layers (GATT writes to `00010002-…`) but not
Sphero's framing. We'd add a small `sphero-dev decode capture.pcap`. It
would unescape packets, check checksums and label DID/CID using the tables
in spherov2. Most of that is already written for the simulator and tests.

**Not recommended:**
- Decompiling the Edu app: spherov2 already did it, and it's the
  part most likely to break the app's terms.
- Reading or changing firmware: not needed, and it risks bricking the
  robot.

## Terms and licensing

I'm not a lawyer, and this isn't legal advice. These are the facts to weigh.

- Sphero's **SDK License Agreement** ships with the first-party RVR SDK
  (`sphero-sdk` on PyPI). It allows personal, academic and research use,
  and it forbids:
  - reverse engineering;
  - using undocumented APIs;
  - public or commercial deployment;
  - building anything that "competes with Sphero or any of its products".

  It applies to people who use *that SDK*. So **don't copy code from it**.
  This repo doesn't.
- Using MIT community libraries, and watching your own robot's Bluetooth
  traffic, doesn't touch that agreement. The Edu app has its own terms,
  which may say more about this; I haven't checked them.
- **Safest framing:** an open-source, personal and educational tool that
  works alongside the Edu app (programs stay pasteable into it), not a
  replacement product. Get advice before selling it or putting it in an app
  store.

## Platforms: the iPad is the hard part

| Option | Works on iPad? | Notes |
|---|---|---|
| Web Bluetooth in Safari | **No** | WebKit has publicly opposed Web Bluetooth and hasn't shipped it. Third-party browsers and extensions (e.g. Bluefy, WebBLE) exist but are niche |
| **Local web UI, laptop does Bluetooth** | **Yes, as the screen** | A laptop or Raspberry Pi runs `sphero-dev` and the Claude call and connects to the robot. The iPad opens `http://laptop.local:8000` in Safari. spherov2 even has a TCP relay adapter (`spherov2.adapter.tcp_server`). The API key stays on the laptop |
| Native iPad app (Swift + CoreBluetooth) | Yes | Full control. You can install your own build on your own iPad with a free Apple account (expires after 7 days); TestFlight or the App Store needs the $99/yr developer program. Needs a Swift port of the protocol and a backend for the API key |
| Chrome Web Bluetooth | Not on iPad | Fine on Mac, Windows, Android and Chromebook |

## Recommended plan

1. **Spike (one evening, needs a laptop with Bluetooth near the robot).**
   Run the checklist above with spherov2 and record the results here.
   - If drive, LEDs and location work, the project is unblocked.
   - If not, do a PacketLogger capture of the Edu app doing the same thing
     and fix our `BOLTPlus` class.
2. **`sphero-dev decode`**, only if step 1 found gaps: turns captures into
   readable commands, and helps work out the LCD.
3. **Prototype: `sphero-dev serve`.** A local web page with a chat box, the
   generated code, a simulated path, and Run / Stop. The pipeline is Claude,
   then the simulator, then the robot over spherov2, as in
   [direct-to-robot-app.md](direct-to-robot-app.md). Open the page from the
   iPad. This reuses almost everything in the repo and needs no app store.
4. **Later, if it's worth it:** a TypeScript port of the protocol for a
   Chrome Web Bluetooth version, or a native iPad app. Both follow from a
   decided step 3; neither is needed to prove the idea.
