"""Where clips land, and refusing to land them on the SD card.

CLAUDE.md #4 says clips go on the USB SSD, never the SD card, because sustained
video writes kill SD cards. Prose does not enforce that — a default path or a
missing symlink silently does the opposite. So the recorder resolves its target
and refuses to start if it is backed by the SD card.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: The Pi's SD card presents as /dev/mmcblk*. USB storage presents as /dev/sd*.
_SD_CARD_PREFIXES = ("/dev/mmcblk",)


class UnsafeClipTarget(RuntimeError):
    """Raised when clips would be written to the SD card."""


@dataclass(frozen=True)
class Target:
    path: Path
    device: str | None
    mountpoint: str | None

    @property
    def on_sd_card(self) -> bool:
        return self.device is not None and self.device.startswith(_SD_CARD_PREFIXES)

    @property
    def known(self) -> bool:
        """False off-target, where there is no /proc/mounts worth consulting."""
        return self.device is not None


def _is_under(path: str, mount: str) -> bool:
    if mount == "/":
        return True
    mount = mount.rstrip("/")
    return path == mount or path.startswith(mount + "/")


def resolve_target(path: str | os.PathLike[str], mounts_text: str) -> Target:
    """Find the block device backing `path` by longest-prefix mount match.

    Pure: takes /proc/mounts content rather than reading it, so it is testable
    off-target against any filesystem layout.
    """
    resolved = Path(path).resolve()
    best: tuple[str, str] | None = None  # (mountpoint, device)

    for line in mounts_text.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        device, mountpoint = fields[0], fields[1].replace("\\040", " ")
        if not _is_under(str(resolved), mountpoint):
            continue
        if best is None or len(mountpoint) > len(best[0]):
            best = (mountpoint, device)

    if best is None:
        return Target(resolved, None, None)
    return Target(resolved, best[1], best[0])


def read_mounts() -> str:
    try:
        return Path("/proc/mounts").read_text()
    except OSError:
        return ""


def check_clip_target(
    path: str | os.PathLike[str],
    *,
    mounts_text: str | None = None,
    allow_sd_card: bool = False,
) -> Target:
    """Resolve the clips directory and refuse the SD card.

    `allow_sd_card` exists as a deliberate, explicit override. It is never a
    default, and the caller has to say it out loud.
    """
    target = resolve_target(path, read_mounts() if mounts_text is None else mounts_text)

    if target.on_sd_card and not allow_sd_card:
        raise UnsafeClipTarget(
            f"{target.path} is on {target.device} (SD card). Sustained video "
            f"writes kill SD cards — see CLAUDE.md #4. Point clips/ at the USB "
            f"SSD:\n    ln -s /mnt/ssd/rack-vision-clips clips\n"
            f"Override with --allow-sd-card only if you mean it."
        )
    return target
