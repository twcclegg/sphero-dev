# Getting code into the Sphero Edu app without copy/paste

**Status: research notes, nothing implemented or verified yet.**

## Findings (October 2026)

From the public pages and browser scripts of `edu.sphero.com` (no API calls
made, nothing signed in):

- `edu.sphero.com` is now **Sphero Central**, a lessons/resources site with
  a program library: "My Content › Programs", `/program/:id/edit`, sharing
  and assigning programs to classes. Old `/remixes/...` links redirect to
  `/programs/`.
- Programs are saved through a GraphQL `upsertProgram` mutation whose
  program is an uploaded **`.lab` file** (the upload box accepts only
  `.lab`). Program records have a `programType` (`block`, `text`, `canvas`
  seen in the scripts), a `code` field and a `labFile` URL.
- So **`.lab` is the Edu app's program file format**, and Sphero Central
  accepts `.lab` uploads. If we can produce a `.lab` file from a `.py` file,
  programs could reach the app by file instead of copy/paste (option 2b
  below).
- `sphero.docsapp.io` (the old Edu JavaScript/Python command docs) doesn't
  answer any more (bad gateway); the Python command docs now seem to live
  only inside the app.

Today the workflow is: write code on a computer (often with an AI
assistant), get the text onto the tablet, paste it into the Edu app's
editor. This page tracks ways to cut out the manual steps.

## What we believe (not yet verified)

- Sphero Edu programs are tied to a Sphero Edu account and sync between
  devices. A program created on one device appears on others signed into the
  same account.
- Programs can be shared by link and assigned to classes (confirmed by the
  findings above).
- `edu.sphero.com` no longer has a code editor: no editor component
  (Monaco, CodeMirror, Blockly) appears in its scripts. Programs are written
  in the app and uploaded or shared as `.lab` files.

## Candidate approaches

Ordered from least to most effort.

1. **Clipboard handoff.** On Apple devices, Universal Clipboard: copy on the
   Mac, paste on the iPad. Zero code. Worth documenting as the default.
2. **Edit on the web, run on the tablet.** Ruled out: Sphero Central has no
   code editor any more (see findings). Uploading a `.lab` file (2b) is the
   web route that's left.
2b. **Generate a `.lab` file.** Learn the format from a Python program
   exported from the app, write `sphero-dev export program.py`, then open
   the file in the app (AirDrop / Files on iPad) or upload it on Sphero
   Central. Next step: export one Python program from the Edu app as
   `.lab` and add it to this repo as a sample. Not yet confirmed: that the
   app can import `.lab` files, and that uploads to Sphero Central show up
   in the app.
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
