"""Read and write Sphero Edu ``.lab`` program files.

A ``.lab`` file is JSON. For a Python text program it looks like::

    {"program_type": "text",
     "data": "15;python&<source code>",
     "robots": [{"id": 19, "name": "Sphero BOLT+"}],
     "name": "My Program",
     "identifier": "AACAD1AE-6DDF-4D83-B7A7-9F8A0719613E",
     "images": [{"large": {"width": 0, "height": 0},
                 "thumbnail": {"width": 0, "height": 0}}]}

This layout comes from one file exported by the Edu app (October 2026).
What the ``15`` in ``data`` means is unknown; we copy it unchanged.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

DATA_PREFIX = "15;python&"

# Robot ids seen in exported files. Add more as they turn up.
ROBOTS = {
    "bolt+": {"id": 19, "name": "Sphero BOLT+"},
}


@dataclass
class LabProgram:
    name: str
    code: str
    robots: list[dict] = field(default_factory=lambda: [dict(ROBOTS["bolt+"])])
    identifier: str = field(default_factory=lambda: str(uuid.uuid4()).upper())


def loads(text: str) -> LabProgram:
    d = json.loads(text)
    if d.get("program_type") != "text":
        raise ValueError(f"not a text program (program_type={d.get('program_type')!r})")
    header, sep, code = d.get("data", "").partition("&")
    if not sep or not header.endswith(";python"):
        raise ValueError(f"not a Python program (data starts {d.get('data', '')[:20]!r})")
    return LabProgram(name=d.get("name", ""), code=code, robots=d.get("robots", []),
                      identifier=d.get("identifier", ""))


def dumps(program: LabProgram) -> str:
    d = {
        "program_type": "text",
        "data": DATA_PREFIX + program.code.rstrip("\n"),
        "robots": program.robots,
        "name": program.name,
        "identifier": program.identifier,
        "images": [{"large": {"width": 0, "height": 0},
                    "thumbnail": {"width": 0, "height": 0}}],
    }
    # Match the app's output: compact, ASCII-only, with "/" escaped as "\/".
    return json.dumps(d, separators=(",", ":"), ensure_ascii=True).replace("/", "\\/")


def read(path: str | Path) -> LabProgram:
    return loads(Path(path).read_text(encoding="utf-8"))


def write(program: LabProgram, path: str | Path) -> None:
    Path(path).write_text(dumps(program), encoding="utf-8")
