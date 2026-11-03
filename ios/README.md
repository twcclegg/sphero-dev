# Sphero Chat (iPad / iPhone)

A chat app for `sphero-dev ask`: type or dictate what the robot should do,
Claude writes and simulates the program, and you tap **Run on robot**.
Replies show the program with syntax highlighting, the simulated and
measured paths as charts, speed over time, and a table of sensor readings
(shareable as CSV). **Export .lab** saves the program for the Sphero Edu
app's Import.

**Status: only partly checked.** I haven't built the SwiftUI app: that needs
Xcode, and this was written on Linux. `SpheroChatCore` (message format, HTTP
client, highlighter) builds and passes its tests on Linux, including a test
against a running `sphero-dev serve` with a fake Claude and robot. Expect some
compile fixes the first time it's opened in Xcode, and it hasn't been used
with a real robot.

## How it fits together

The app is a thin client. The computer next to the robot does the work: it
runs `sphero-dev serve`, which talks to Claude (your subscription through the
`claude` CLI, or `ANTHROPIC_API_KEY`), runs the simulator, and drives the
robot over Bluetooth like `sphero-dev ask` does.

```
iPad  --Wi-Fi, HTTP + token-->  computer: sphero-dev serve  --Bluetooth-->  BOLT+
```

## Run it

1. On the computer (Linux or macOS, next to the robot):

   ```bash
   pip install -e '.[ai]'
   sphero-dev serve --robot BP-5FBB --space 80
   ```

   It prints the address and token to enter in the app. The token is kept
   in `~/.config/sphero-dev/serve-token`; delete that file for a new one.
   Options match `sphero-dev ask` (`--max-speed`, `--seconds`, `--space`,
   `--model`, `--via`) plus `--port` (8765).

2. On a Mac with Xcode 15+:

   ```bash
   brew install xcodegen
   cd ios && xcodegen && open SpheroChat.xcodeproj
   ```

   Choose your team under Signing & Capabilities and run on the iPad.

3. In the app, open Settings, enter the server and token, and tap **Test
   connection**. iOS asks for Local Network access the first time; allow it.

## Notes

- **Stop** (in the message and the input bar) halts the robot through the
  server. Every run also stops at `--seconds` and is capped at `--max-speed`.
- The server keeps conversations in memory. If it restarts, the app keeps its
  history but Claude starts afresh.
- The server speaks plain HTTP with a bearer token. Use it on a home network
  you trust, not on public Wi-Fi.
- The token is stored in the app's UserDefaults, not the Keychain.
- Dictation uses Apple's speech recognizer, on the device when supported.
- The server API and message format are documented at the top of
  `src/sphero_dev/serve.py`.

## Testing

```bash
cd ios/SpheroChatCore && swift test           # Linux or macOS
# Against a live server with a fake Claude and robot:
python tests/serve_fixture.py 18765 tok &
SPHERO_TEST_SERVER=127.0.0.1:18765 SPHERO_TEST_TOKEN=tok swift test
```
