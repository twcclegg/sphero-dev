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

   For the app, give it a certificate (next section); iOS won't talk plain
   HTTP to it.

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
- The token is stored in the app's UserDefaults, not the Keychain.
- Dictation uses Apple's speech recognizer, on the device when supported.
- The server API and message format are documented at the top of
  `src/sphero_dev/serve.py`.

## HTTPS with a real certificate

`sphero.clegg.dev` is a public DNS name that points at the laptop's address
on the home network (192.168.1.102). Only devices at home can reach it, and
the router's port forwarding isn't involved. The Let's Encrypt certificate
comes from a DNS-01 check through the GoDaddy API, so the server never has to
be reachable from the internet. The token is the one minecraft.clegg.dev's
DDNS already uses (`~/.config/godaddy/api.env`).

```bash
go install github.com/go-acme/lego/v4/cmd/lego@latest   # once; lands in ~/go/bin
PATH=$HOME/go/bin:$PATH deploy/cert.sh                  # gets the certificate
L=~/.local/share/sphero-dev/lego/certificates
sphero-dev serve --cert $L/sphero.clegg.dev.crt --key $L/sphero.clegg.dev.key \
    --name sphero.clegg.dev --robot BP-5FBB
# Renew automatically (daily check; renews 30 days before expiry):
cp deploy/sphero-dev-cert.* ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now sphero-dev-cert.timer
```

`serve` reloads the certificate when the file changes, so renewals need no
restart. `deploy/cert.sh` also re-points the DNS record if the laptop's
address changes; a DHCP reservation for the laptop in the router avoids that.

**The router's DNS won't answer for it.** It has DNS rebinding protection:
it drops answers where a public name points at a home address. So on the
iPad, set the Wi-Fi network's DNS by hand: Settings → Wi-Fi → (i) next to
the network → Configure DNS → Manual, remove the router's server, add
`1.1.1.1` and `1.0.0.1`. (This laptop already uses 1.1.1.1.)

## Testing

```bash
cd ios/SpheroChatCore && swift test           # Linux or macOS
# Against a live server with a fake Claude and robot:
python tests/serve_fixture.py 18765 tok &
SPHERO_TEST_SERVER=http://127.0.0.1:18765 SPHERO_TEST_TOKEN=tok swift test
```
