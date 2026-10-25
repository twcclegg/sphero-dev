# Getting code into the Sphero Edu app without copy/paste

**Status: research notes, nothing implemented or verified yet.**

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
5. **Skip the app.** For desktop-capable users, run the same program through
   a local shim over spherov2 instead of the app (see the roadmap in the
   README). Doesn't help iPad-only classrooms.

## Open questions

- Do Text (Python) programs sync across devices on the same account?
- Does `edu.sphero.com` expose program import/export (file upload)?
- Is there a public or documented API for programs?
- What do Sphero's terms say about automated access?

If you find answers, update this page with the source and date.
