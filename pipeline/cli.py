"""Entry point: rack-vision capture.

    python -m pipeline --dry-run              # off-target: print the graph
    python -m pipeline --source test --sink auto --duration 5
    sudo python -m pipeline                   # on the Pi
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import config as config_mod
from . import controls, detect, storage
from .formats import CaptureFormat
from .graph import Sink, Source, build

log = logging.getLogger("rack_vision")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rack-vision", description=__doc__)
    p.add_argument("--config", default="config.toml", type=Path)
    p.add_argument("--source", choices=["auto", "v4l2", "test"], default="auto")
    p.add_argument("--sink", choices=[s.value for s in Sink], default="kms")
    p.add_argument(
        "--format",
        choices=[f.value for f in CaptureFormat],
        help="override capture format instead of detecting it",
    )
    p.add_argument("--device", help="override camera.device")
    p.add_argument(
        "--dry-run", action="store_true",
        help="print the pipeline and exit; needs no camera and no GStreamer",
    )
    p.add_argument(
        "--allow-sd-card", action="store_true",
        help="permit writing clips to the SD card (see CLAUDE.md #4)",
    )
    p.add_argument("--duration", type=float, help="stop after N seconds")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _resolve_source(requested: str, device: str | None) -> Source:
    if requested == "v4l2":
        return Source.V4L2
    if requested == "test":
        return Source.TEST
    # auto: a real device if one is configured and present, else synthetic.
    if device and Path(device).exists():
        return Source.V4L2
    return Source.TEST


def _resolve_format(
    args: argparse.Namespace, source: Source, device: str | None, cfg: config_mod.Config
) -> CaptureFormat:
    explicit = args.format or cfg.camera.format
    if explicit:
        return CaptureFormat(explicit)

    if source is Source.TEST:
        return CaptureFormat.RAW_YUY2

    modes = detect.probe_device(device)  # type: ignore[arg-type]
    mode = detect.select_mode(modes, cfg.camera.width, cfg.camera.height, cfg.camera.framerate)
    if mode is None:
        advertised = "\n  ".join(str(m) for m in modes) or "(none)"
        raise SystemExit(
            f"camera cannot deliver {cfg.camera.width}x{cfg.camera.height}"
            f"@{cfg.camera.framerate}. Advertised:\n  {advertised}\n"
            "Not falling back to another geometry — that would change the frame "
            "coordinate system and invalidate calibration (CLAUDE.md #1)."
        )
    log.info("detected capture mode: %s", mode)
    return mode.fmt


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = config_mod.load(args.config) if args.config.exists() else config_mod.Config()
    device = args.device or cfg.camera.device
    source = _resolve_source(args.source, device)
    fmt = _resolve_format(args, source, device, cfg)

    clips_dir = Path(cfg.storage.clips_dir).resolve()
    target = storage.check_clip_target(clips_dir, allow_sd_card=args.allow_sd_card)
    if not target.known:
        log.warning("could not determine the device backing %s", clips_dir)

    spec = build(
        fmt=fmt,
        source=source,
        sink=Sink(args.sink),
        device=device,
        clips_dir=str(clips_dir),
        width=cfg.camera.width,
        height=cfg.camera.height,
        framerate=cfg.camera.framerate,
        segment_seconds=cfg.replay.segment_seconds,
        ring_segments=cfg.replay.ring_segments,
    )

    if args.dry_run:
        print(f"# source={source.value} format={fmt.value} sink={args.sink}")
        print(f"# clips -> {target.path} (device: {target.device or 'unknown'})")
        print(spec.description)
        for note in spec.notes:
            print(f"\n# note: {note}")
        return 0

    if source is Source.V4L2 and device:
        # Config saying tracking is off does not make it off on the device.
        for action in controls.enforce_fixed_camera(device):
            log.info("fixed-camera: %s", action)

    clips_dir.mkdir(parents=True, exist_ok=True)
    from .runtime import run  # noqa: PLC0415 — deferred so --dry-run needs no gi

    return run(spec, timeout_seconds=args.duration)


def run_cli(argv: list[str] | None = None) -> int:
    """Console entry point: turn operational failures into clean messages.

    `main` raises so tests can assert on the exception; this wrapper is what a
    person invokes, and a person should not get a traceback because a camera is
    absent or the clips directory points at the SD card.
    """
    from .config import ConfigError, ConstraintViolation
    from .runtime import GStreamerUnavailable
    from .storage import UnsafeClipTarget

    try:
        return main(argv)
    except (
        ConfigError,
        ConstraintViolation,
        UnsafeClipTarget,
        GStreamerUnavailable,
        RuntimeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_cli())
