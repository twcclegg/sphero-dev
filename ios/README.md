# Sphero Chat (iPad / iPhone)

Type or dictate what the robot should do. Claude writes an Edu-app program
and checks it in the simulator; you tap **Run on robot**. Replies show the
program with syntax highlighting, the simulated and measured paths as charts,
speed over time, and a table of sensor readings (shareable as CSV). **Export
.lab** saves the program for the Sphero Edu app's Import.

**Everything runs on the iPad.** No laptop or server: the app talks to the
robot over Bluetooth and to Claude over the internet.

**Status: not built yet.** It was written on Linux, which can't build iOS
apps. What has been checked there:
- the Python side (`src/sphero_dev/app.py`, `ios_adapter.py`, `claude_api.py`,
  `numpy_lite.py`, in-thread simulation): pytest, with fakes for Claude,
  Bluetooth and the robot;
- `SpheroChat/Python/PythonBridge.c`: compiled and run against Linux's Python
  with fake Bluetooth functions;
- `SpheroChatCore` (message format, highlighter): `swift test` on Linux.

The SwiftUI screens and the CoreBluetooth code have never been compiled.
Expect fixes the first time it's opened in Xcode, and it hasn't driven a
robot yet.

## How it fits together

```
SwiftUI screens ── ChatStore ── PythonRuntime ──> embedded CPython 3.13
                                                   sphero_dev.app
                                                    ├─ ask.Conversation ── claude_api ──> Claude API (HTTPS)
                                                    ├─ simulator (in a thread, with a watchdog)
                                                    └─ spherov2 + BOLTPlus ── ios_adapter
                                                                                │  _sphero_ble (C)
CoreBluetooth <── BluetoothBridge.swift <────────────────────────────────────────┘
```

- **Python** comes from BeeWare's
  [Python-Apple-support](https://github.com/beeware/Python-Apple-support)
  (`Python.xcframework`). The app's code is the same `sphero_dev` package the
  CLI uses, so programs are Edu-app Python and export to the Sphero Edu app.
- **Bluetooth**: spherov2 does the Sphero protocol in Python. Its adapter
  (`ios_adapter.IOSAdapter`) passes scan / connect / write / notify to
  `BluetoothBridge.swift` through a small built-in C module.
- **Claude**: the Messages API, with your Anthropic API key, kept in the
  Keychain. Your Claude subscription can't be used from a third-party app as
  far as I know; if Anthropic offers a sign-in for that, it would replace
  the key in Settings and `claude_api.ApiClient`.

## Build it (Mac with Xcode 15.3+)

```bash
brew install xcodegen
cd ios
scripts/fetch-python.sh     # Python.xcframework + spherov2/certifi (once)
xcodegen                    # writes SpheroChat.xcodeproj
open SpheroChat.xcodeproj
```

Choose your team under Signing & Capabilities, connect the iPad and Run.
With a free Apple account the app stops opening after 7 days until you
run it from Xcode again; the paid developer program removes that limit.

The build phase `scripts/install-python.sh` copies Python's standard library,
`src/sphero_dev` and the packages into the app.

## Use it

1. Settings: paste an Anthropic API key (console.anthropic.com). Tap **Find
   robots** and pick yours (BOLT+ names start `BP-`). Set the top speed, the
   time limit and the floor space.
2. Wake the robot, and close the Sphero Edu app so it isn't connected.
3. Ask for something, check the program and the simulated path, tap **Run
   on robot**, aim the robot so its blue tail light faces you. **Stop** halts
   it at once; every run also stops at the time limit.

Conversations with Claude last until the app closes; the history on screen
is kept.

## Testing

```bash
python -m pytest tests/test_ios_python.py      # the Python side, on any computer
cd ios/SpheroChatCore && swift test            # Linux or macOS
```
