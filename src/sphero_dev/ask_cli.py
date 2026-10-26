"""The interactive side of ``sphero-dev ask``: show, save, run, revise."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import lab
from .ask import AskError, Conversation, Proposal

MENU = "[r]un on robot, [s]ave, [q]uit, or type a change: "


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _dim(text: str) -> None:
    print(f"\033[2m{text}\033[0m" if sys.stdout.isatty() else text)


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "program"


def _show(p: Proposal) -> None:
    rule = "-" * 72
    print(f"\n{rule}\n{p.title}\n{rule}\n{p.code.rstrip()}\n{rule}")
    print(p.summary)
    print("\nSimulator (rough; no slipping or collisions):")
    for line in p.sim_report.splitlines()[:3]:
        print(f"  {line}")


def _save(p: Proposal, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    py = out_dir / f"{_slug(p.title)}.py"
    py.write_text(p.code.rstrip() + "\n", encoding="utf-8")
    dot_lab = py.with_suffix(".lab")
    lab.write(lab.LabProgram(name=p.title, code=p.code), dot_lab)
    print(f"Saved {py} and {dot_lab} (import the .lab in the Sphero Edu app).")


def ask_main(args: argparse.Namespace) -> int:
    try:
        import anthropic
    except ImportError:
        print("sphero-dev ask needs the Anthropic SDK (Python 3.10+):\n"
              "  pip install 'sphero-dev[ai]'", file=sys.stderr)
        return 1
    from .cli import run_on_robot

    try:
        client = anthropic.Anthropic()
    except anthropic.AnthropicError as e:
        print(f"Couldn't set up the Anthropic client: {e}\n"
              "Set ANTHROPIC_API_KEY (from console.anthropic.com).", file=sys.stderr)
        return 1
    convo = Conversation(client, max_speed=args.max_speed, seconds=args.seconds,
                         effort=args.effort, status=_dim)

    message = " ".join(args.request) or _input("What should the robot do? ")
    while message:
        print("Asking Claude...")
        try:
            reply = convo.send(message)
        except AskError as e:
            print(e)
            message = _input("Rephrase, or press Enter to quit: ")
            continue
        except anthropic.AuthenticationError:
            print("The API key was rejected. Set ANTHROPIC_API_KEY to a valid key.",
                  file=sys.stderr)
            return 1
        except anthropic.RateLimitError:
            print("Rate limited by the API. Wait a minute and try again.", file=sys.stderr)
            return 1
        except anthropic.APIStatusError as e:
            print(f"API error {e.status_code}: {e.message}", file=sys.stderr)
            return 1
        except anthropic.APIConnectionError as e:
            print(f"Couldn't reach the Anthropic API: {e}", file=sys.stderr)
            return 1
        except TypeError as e:
            # The SDK raises this at request time when it finds no credentials.
            if "authentication" not in str(e):
                raise
            print("No Anthropic credentials found. Set ANTHROPIC_API_KEY (create a key at "
                  "console.anthropic.com).", file=sys.stderr)
            return 1

        if reply.proposal is None:
            # Usually a question back to the user.
            print(reply.text)
            message = _input("> ")
            continue

        proposal = reply.proposal
        _show(proposal)
        ran = False
        while True:
            choice = _input(MENU)
            if choice.lower() in ("", "q", "quit"):
                return 0
            if choice.lower() in ("r", "run"):
                try:
                    run_on_robot(proposal.code, args.robot, args.seconds, args.max_speed,
                                 f"{_slug(proposal.title)}.py")
                except Exception as e:  # no robot found, Bluetooth off, ...
                    print(f"Couldn't run it on the robot: {e}")
                    continue
                ran = True
                print("Done. Tell me how it went to improve it, or choose again.")
            elif choice.lower() in ("s", "save"):
                _save(proposal, Path(args.out_dir))
            else:
                message = f"I ran it on the real robot. {choice}" if ran else choice
                break
    return 0
