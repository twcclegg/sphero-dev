"""Just enough of numpy and transforms3d for spherov2, where numpy isn't installed (iOS).

spherov2's ``sphero_edu`` imports both, for one line: the vertical acceleration,
``-matmul(inv(euler2mat(*deg2rad(rpy), axes='szxy')), acc)[1]``. :func:`install`
puts small pure-Python stand-ins in ``sys.modules`` when the real ones are
missing; the tests check them against the real libraries.
"""

from __future__ import annotations

import math
import sys
import types
from typing import Sequence

Matrix = list[list[float]]

# transforms3d's axis table: firstaxis, parity, repetition, frame.
_AXES = {"sxyz": (0, 0, 0, 0), "szxy": (2, 0, 0, 0), "syzx": (1, 0, 0, 0)}
_NEXT_AXIS = [1, 2, 0, 1]


def deg2rad(values: Sequence[float]) -> list[float]:
    return [math.radians(v) for v in values]


def euler2mat(ai: float, aj: float, ak: float, axes: str = "sxyz") -> Matrix:
    i, parity, repetition, frame = _AXES[axes]
    if repetition:
        raise NotImplementedError(f"axes {axes!r}")
    j = _NEXT_AXIS[i + parity]
    k = _NEXT_AXIS[i - parity + 1]
    if frame:
        ai, ak = ak, ai
    if parity:
        ai, aj, ak = -ai, -aj, -ak
    si, sj, sk = math.sin(ai), math.sin(aj), math.sin(ak)
    ci, cj, ck = math.cos(ai), math.cos(aj), math.cos(ak)
    cc, cs, sc, ss = ci * ck, ci * sk, si * ck, si * sk
    m = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    m[i][i], m[i][j], m[i][k] = cj * ck, sj * sc - cs, sj * cc + ss
    m[j][i], m[j][j], m[j][k] = cj * sk, sj * ss + cc, sj * cs - sc
    m[k][i], m[k][j], m[k][k] = -sj, cj * si, cj * ci
    return m


def inv(m: Matrix) -> Matrix:
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def matmul(m: Matrix, v: Sequence[float]) -> list[float]:
    return [sum(r * x for r, x in zip(row, v)) for row in m]


def install() -> bool:
    """Provide ``numpy`` and ``transforms3d.euler`` if they can't be imported.

    Returns True if the stand-ins were installed.
    """
    try:
        import numpy  # noqa: F401
        import transforms3d.euler  # noqa: F401
        return False
    except ImportError:
        pass
    np = types.ModuleType("numpy")
    np.deg2rad = deg2rad  # type: ignore[attr-defined]
    np.matmul = matmul  # type: ignore[attr-defined]
    np.linalg = types.SimpleNamespace(inv=inv)  # type: ignore[attr-defined]
    t3d = types.ModuleType("transforms3d")
    euler = types.ModuleType("transforms3d.euler")
    euler.euler2mat = euler2mat  # type: ignore[attr-defined]
    t3d.euler = euler  # type: ignore[attr-defined]
    sys.modules.update({"numpy": np, "transforms3d": t3d, "transforms3d.euler": euler})
    return True
