# Getting code into the Sphero Edu app without copy/paste

**Status: research notes, nothing implemented or verified yet.**

Research so far was done without access to Sphero's sites
(`edu.sphero.com`, `sdk.sphero.com`, `sphero.docsapp.io` were unreachable
from the environment used), so the items below come from general knowledge
and from spherov2's source, which links `edu.sphero.com/remixes/...` pages.

Today the workflow is: write code on a computer (often with an AI
assistant), get the text onto the tablet, paste it into the Edu app's
editor. This page tracks ways to cut out the manual steps.

## What we believe (not yet verified)

- Sphero Edu programs are tied to a Sphero Edu account and sync between
  devices. A program created on one device appears on others signed into the
  same account.
- The Edu app also runs in a web browser at `edu.sphero.com` (and as
  desktop/Chromebook apps), with the same text editor.
- Programs can be shared and "remixed" by link.

## Candidate approaches

Ordered from least to most effort.

1. **Clipboard handoff.** On Apple devices, Universal Clipboard: copy on the
   Mac, paste on the iPad. Zero code. Worth documenting as the default.
2. **Edit on the web, run on the tablet.** If programs sync, paste into the
   Edu web editor on the same computer as the code, then open the synced
   program on the tablet. Needs confirming that text programs sync and how
   quickly.
3. **Browser automation of the web editor.** A script (e.g. Playwright) that
   signs into `edu.sphero.com`, opens a program, and replaces its text with a
   local file. Fragile against UI changes, but needs no private API.
4. **The Edu web app's own API.** The web app must save programs to a
   backend. If that API is stable, a small CLI could do
   `sphero-dev push examples/edu_app/circles.py --program "Circles"`.
   Before building on it, check Sphero's terms of service and ask Sphero
   whether a supported route exists.
5. **Skip the app.** Run the same program from a computer with
   `sphero-dev run` ([shim.md](shim.md)), which now exists. Doesn't help
   iPad-only classrooms. The longer-term version of this is a Claude-powered
   app that talks to the robot directly:
   [direct-to-robot-app.md](direct-to-robot-app.md).

## How to research options 2-4

With network access to `edu.sphero.com`:

1. Sign in on the web app, create a Python program on a tablet, and see if
   and how fast it appears on the web (option 2).
2. Look for import/export, "download", "upload", or share-link features in
   the program menu (options 2-4).
3. Read the terms of service on automated access *before* inspecting the
   web app's network traffic for its save/load calls (option 4). If the
   terms forbid it, or Sphero offers a supported route, use that instead.

## Open questions

- Do Text (Python) programs sync across devices on the same account?
- Does `edu.sphero.com` expose program import/export (file upload)?
- Is there a public or documented API for programs?
- What do Sphero's terms say about automated access?

If you find answers, update this page with the source and date.
