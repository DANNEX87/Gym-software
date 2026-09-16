"""Find and neutralise any on-device reframing, on the target.

CLAUDE.md #1 is the constraint most at risk from this specific hardware: the
Connect is a smart video bar whose selling point is auto-framing, and that happens
upstream of the USB boundary. A camera that digitally pans or switches lens
mid-set is a moving camera, and it corrupts frame-relative measurements without
ever looking wrong.

Config asserting `auto_framing = false` does not make it false on the device. So
this enumerates the real V4L2 controls and neutralises what it finds — and reports
anything it cannot, because a control that is absent here may still be driven by
the vendor's own app.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

#: Substrings that suggest a control reframes the image.
_FRAMING_HINTS = (
    "framing", "tracking", "track", "face", "speaker", "roi",
    "pan", "tilt", "zoom", "compose", "crop",
)

_CONTROL_RE = re.compile(
    r"^\s*(?P<name>\w+)\s+0x[0-9a-fA-F]+\s+\((?P<type>\w+)\)\s*:\s*(?P<rest>.*)$"
)


@dataclass(frozen=True)
class Control:
    name: str
    type: str
    default: int | None
    value: int | None

    @property
    def is_framing(self) -> bool:
        lowered = self.name.lower()
        return any(hint in lowered for hint in _FRAMING_HINTS)

    @property
    def neutral(self) -> int | None:
        """The value that means 'do nothing'.

        Booleans go to 0 (off). PTZ integers go to the driver's own default rather
        than 0, because 0 is not necessarily a valid or neutral zoom.
        """
        if self.type == "bool":
            return 0
        return self.default


def parse_controls(text: str) -> list[Control]:
    """Parse `v4l2-ctl --list-ctrls` output. Pure."""
    controls: list[Control] = []
    for line in text.splitlines():
        m = _CONTROL_RE.match(line)
        if not m:
            continue
        rest = m.group("rest")
        fields = dict(re.findall(r"(\w+)=(-?\d+)", rest))
        controls.append(
            Control(
                name=m.group("name"),
                type=m.group("type"),
                default=int(fields["default"]) if "default" in fields else None,
                value=int(fields["value"]) if "value" in fields else None,
            )
        )
    return controls


def framing_controls(controls: list[Control]) -> list[Control]:
    return [c for c in controls if c.is_framing]


def needs_change(controls: list[Control]) -> list[Control]:
    """Framing controls not already sitting at their neutral value."""
    out = []
    for c in framing_controls(controls):
        neutral = c.neutral
        if neutral is not None and c.value is not None and c.value != neutral:
            out.append(c)
    return out


def read_controls(device: str, timeout: float = 15.0) -> list[Control]:
    if shutil.which("v4l2-ctl") is None:
        raise RuntimeError("v4l2-ctl not found — this runs on the Pi")
    out = subprocess.run(
        ["v4l2-ctl", "-d", device, "--list-ctrls"],
        capture_output=True, text=True, timeout=timeout, check=True,
    )
    return parse_controls(out.stdout)


def enforce_fixed_camera(device: str) -> list[str]:
    """Set every framing control to neutral. Returns a log of what changed.

    Does not raise if a control refuses to change — it reports it, because the
    honest outcome is 'this camera would not let us turn it off', which belongs in
    HARDWARE.md rather than in a swallowed exception.
    """
    actions: list[str] = []
    controls = read_controls(device)
    found = framing_controls(controls)

    if not found:
        actions.append(
            "no framing-related V4L2 controls exposed — this does NOT prove the "
            "camera is not reframing internally; verify by walking the frame "
            "(HARDWARE.md §3)"
        )
        return actions

    for c in needs_change(controls):
        try:
            subprocess.run(
                ["v4l2-ctl", "-d", device, f"--set-ctrl={c.name}={c.neutral}"],
                capture_output=True, text=True, timeout=15, check=True,
            )
            actions.append(f"{c.name}: {c.value} -> {c.neutral}")
        except subprocess.CalledProcessError as exc:
            actions.append(
                f"{c.name}: REFUSED ({exc.stderr.strip() or 'no detail'}) — "
                f"record this in HARDWARE.md §3"
            )
    return actions
