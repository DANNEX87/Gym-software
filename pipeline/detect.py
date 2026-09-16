"""Discover what the camera can actually do, at runtime, on the target.

Nothing here is hardcoded per CLAUDE.md #5: the capture mode comes from parsing
real `v4l2-ctl` output on the Pi. The parser itself is pure, so it is testable
off-target against captured fixtures.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from .formats import PREFERENCE, CaptureFormat, from_fourcc


@dataclass(frozen=True)
class Mode:
    """One (format, resolution) the device advertises, with its framerates."""

    fmt: CaptureFormat
    fourcc: str
    width: int
    height: int
    framerates: tuple[float, ...]

    def supports(self, fps: float, tolerance: float = 0.5) -> bool:
        return any(abs(f - fps) <= tolerance for f in self.framerates)

    def __str__(self) -> str:
        rates = ",".join(f"{f:g}" for f in self.framerates)
        return f"{self.fourcc} {self.width}x{self.height} @ [{rates}]"


_FORMAT_RE = re.compile(r"^\s*\[\d+\]:\s*'(\w+)'")
_SIZE_RE = re.compile(r"^\s*Size:\s*Discrete\s+(\d+)x(\d+)")
_FPS_RE = re.compile(r"Interval:\s*Discrete\s+[\d.]+s\s+\(([\d.]+)\s*fps\)")
_STEPWISE_RE = re.compile(r"^\s*Size:\s*(Stepwise|Continuous)")


class StepwiseOnly(RuntimeError):
    """Device reports only stepwise/continuous sizes, which we do not yet handle.

    Raised rather than returning an empty list, so this surfaces as a real finding
    to record in HARDWARE.md instead of looking like a camera with no modes.
    """


def parse_formats(text: str) -> list[Mode]:
    """Parse `v4l2-ctl --list-formats-ext` output into modes.

    Unknown fourccs are skipped — we only build pipelines for formats we handle.
    """
    modes: list[Mode] = []
    fourcc: str | None = None
    size: tuple[int, int] | None = None
    rates: list[float] = []
    saw_stepwise = False

    def flush() -> None:
        nonlocal size, rates
        if fourcc and size:
            fmt = from_fourcc(fourcc)
            if fmt is not None:
                modes.append(
                    Mode(fmt, fourcc.upper(), size[0], size[1], tuple(rates))
                )
        size, rates = None, []

    for line in text.splitlines():
        if m := _FORMAT_RE.match(line):
            flush()
            fourcc = m.group(1)
        elif m := _SIZE_RE.match(line):
            flush()
            size = (int(m.group(1)), int(m.group(2)))
        elif _STEPWISE_RE.match(line):
            flush()
            saw_stepwise = True
        elif m := _FPS_RE.search(line):
            rates.append(float(m.group(1)))
    flush()

    if not modes and saw_stepwise:
        raise StepwiseOnly(
            "device advertises only stepwise/continuous sizes; record the raw "
            "v4l2-ctl output in HARDWARE.md and extend parse_formats()"
        )
    return modes


def select_mode(
    modes: list[Mode], width: int, height: int, fps: float
) -> Mode | None:
    """Pick the cheapest-to-handle mode matching the requested geometry.

    Walks PREFERENCE so H.264 wins over MJPEG wins over raw. Returns None if
    nothing matches, which the caller must treat as a hard failure rather than
    silently falling back to a different resolution — geometry changes break
    calibration (CLAUDE.md #1).
    """
    for fmt in PREFERENCE:
        for mode in modes:
            if (
                mode.fmt is fmt
                and mode.width == width
                and mode.height == height
                and mode.supports(fps)
            ):
                return mode
    return None


def probe_device(device: str, timeout: float = 15.0) -> list[Mode]:
    """Run v4l2-ctl against a real device. Target-only; raises off-target."""
    if shutil.which("v4l2-ctl") is None:
        raise RuntimeError(
            "v4l2-ctl not found — this runs on the Pi. For off-target work use "
            "the test source (--source test)."
        )
    out = subprocess.run(
        ["v4l2-ctl", "-d", device, "--list-formats-ext"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return parse_formats(out.stdout)
