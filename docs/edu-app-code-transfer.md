# Getting code into the Sphero Edu app without copy/paste

**Status: a working route exists.** `sphero-dev export` makes a `.lab`
file that the Edu app imports (tested on iPad, BOLT+ program, Oct 2026):

1. `sphero-dev export program.py --name "My Program"`
2. Get the `.lab` file onto the iPad (AirDrop, Files, iCloud Drive).
3. In the Edu app, use its **Import** option and pick the file.

Opening the file from the Files app does **not** work: it launches the app
but imports nothing, for the app's own exports too.

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
2b. **Generate a `.lab` file.** *Works.* `sphero-dev export
   program.py` writes `program.lab`, and `sphero-dev import program.lab`
   extracts the code. The format was learned from a BOLT+ program exported
   from the app (`tests/data/circles_bolt_plus.lab`); see "The `.lab`
   format" below.

   *Tested (iPad, Oct 2026):* a generated `.lab` imports through the app's
   own Import option. Opening any `.lab` (generated or app-exported) from
   the Files app launches Sphero Edu without importing it. Sphero Central
   uploads haven't been tried.
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

## The `.lab` format

A `.lab` file is one line of JSON. From an Edu-app export (October 2026):

```json
{"program_type":"text",
 "data":"15;python&# Fast circles about 1 meter across.\n...",
 "robots":[{"id":19,"name":"Sphero BOLT+"}],
 "name":"Untitled Program (2)",
 "identifier":"AACAD1AE-6DDF-4D83-B7A7-9F8A0719613E",
 "images":[{"large":{"width":0,"height":0},"thumbnail":{"width":0,"height":0}}]}
```

- `data` is `15;python&` followed by the source code, with the trailing
  newline removed. The meaning of `15` is unknown (an editor or format
  version?); `sphero-dev` copies it.
- `robots` lists the robot types the program is for. Only BOLT+ (`19`) is
  known so far; exports for other robots would fill in the table in
  `src/sphero_dev/lab.py`.
- `identifier` is an uppercase UUID. `sphero-dev export` makes a new one per
  file, so importing it twice probably creates two programs.
- The app writes compact JSON with `/` escaped as `\/`; `sphero-dev`
  matches it byte for byte.

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
