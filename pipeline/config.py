"""Load and validate config.toml.

Two jobs beyond parsing. First, geometry is never guessed: absent values stay
absent rather than defaulting to something plausible, because a plausible-but-wrong
calibration constant corrupts every metric downstream and looks fine doing it.

Second, the fixed-camera constraint is enforced here rather than trusted. CLAUDE.md
#1 is permanent, so config that switches tracking on is rejected at load.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConstraintViolation(ValueError):
    """Config contradicts a permanent constraint in CLAUDE.md."""


class ConfigError(ValueError):
    """Config is malformed or internally inconsistent."""


@dataclass(frozen=True)
class CameraConfig:
    device: str | None = None
    #: None means "detect at runtime". An explicit value forces that format and
    #: fails loudly if the camera cannot deliver it.
    format: str | None = None
    width: int = 1920
    height: int = 1080
    framerate: int = 30
    auto_framing: bool = False
    tracking: bool = False


@dataclass(frozen=True)
class ReplayConfig:
    segment_seconds: int = 10
    ring_segments: int = 12
    loop: bool = True


@dataclass(frozen=True)
class StorageConfig:
    clips_dir: str = "clips"


@dataclass(frozen=True)
class GeometryConfig:
    """Mount geometry. Unset until measured — see CLAUDE.md #5."""

    height_m: float | None = None
    distance_m: float | None = None

    @property
    def calibrated(self) -> bool:
        return self.height_m is not None and self.distance_m is not None


@dataclass(frozen=True)
class Config:
    camera: CameraConfig = field(default_factory=CameraConfig)
    replay: ReplayConfig = field(default_factory=ReplayConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    geometry: GeometryConfig = field(default_factory=GeometryConfig)


def _section(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a table, got {type(value).__name__}")
    return value


def from_dict(data: dict) -> Config:
    cam_raw = _section(data, "camera")

    # CLAUDE.md #1 — permanent, and not a preference to be re-litigated in config.
    for key in ("auto_framing", "tracking"):
        if cam_raw.get(key) is True:
            raise ConstraintViolation(
                f"camera.{key} = true contradicts CLAUDE.md #1: the camera is FIXED. "
                "Every measurement is frame-relative, so on-device reframing corrupts "
                "the data silently. This is not configurable."
            )

    camera = CameraConfig(
        device=cam_raw.get("device"),
        format=cam_raw.get("format") or None,
        width=int(cam_raw.get("width", 1920)),
        height=int(cam_raw.get("height", 1080)),
        framerate=int(cam_raw.get("framerate", 30)),
        auto_framing=False,
        tracking=False,
    )

    rep_raw = _section(data, "replay")
    replay = ReplayConfig(
        segment_seconds=int(rep_raw.get("segment_seconds", 10)),
        ring_segments=int(rep_raw.get("ring_segments", 12)),
        loop=bool(rep_raw.get("loop", True)),
    )
    if replay.segment_seconds < 1:
        raise ConfigError("replay.segment_seconds must be >= 1")
    if replay.ring_segments < 2:
        raise ConfigError("replay.ring_segments must be >= 2 (one to write, one to replay)")

    geo_raw = _section(data, "geometry")
    geometry = GeometryConfig(
        height_m=geo_raw.get("height_m"),
        distance_m=geo_raw.get("distance_m"),
    )

    sto_raw = _section(data, "storage")
    storage = StorageConfig(clips_dir=sto_raw.get("clips_dir", "clips"))

    return Config(camera=camera, replay=replay, storage=storage, geometry=geometry)


def load(path: str | Path = "config.toml") -> Config:
    with open(path, "rb") as fh:
        return from_dict(tomllib.load(fh))
