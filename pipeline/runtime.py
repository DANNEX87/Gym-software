"""Instantiate and run a GraphSpec. The only module that touches GStreamer.

Kept deliberately thin: every decision worth testing was already made in `graph`,
so this does not need to run off-target for the project to be developable there.
"""

from __future__ import annotations

import logging
import signal
from typing import Any

from .graph import GraphSpec

log = logging.getLogger(__name__)


class GStreamerUnavailable(RuntimeError):
    pass


def _gst() -> Any:
    """Import GStreamer lazily so this package imports fine without it."""
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
    except (ImportError, ValueError) as exc:
        raise GStreamerUnavailable(
            "GStreamer/PyGObject unavailable. This runs on the Pi; install with\n"
            "    sudo apt install python3-gi gstreamer1.0-tools "
            "gstreamer1.0-plugins-{base,good,bad,libav}\n"
            "Off-target, use --dry-run to inspect the pipeline without running it."
        ) from exc

    if not Gst.is_initialized():
        Gst.init(None)
    return Gst


def missing_elements(spec: GraphSpec) -> list[str]:
    """Element names in the description that this GStreamer install lacks.

    Checked before launching so a missing plugin reports as itself rather than as
    an opaque parse failure.
    """
    Gst = _gst()
    registry = Gst.Registry.get()

    names: set[str] = set()
    for line in spec.description.splitlines():
        for token in line.split(" ! "):
            token = token.strip()
            # Skip caps filters and tee back-references; only elements have factories.
            if not token or token.startswith(("video/", "image/", "t.")):
                continue
            names.add(token.split()[0])

    return sorted(n for n in names if registry.find_feature(n, Gst.ElementFactory) is None)


def run(spec: GraphSpec, *, timeout_seconds: float | None = None) -> int:
    """Launch the pipeline and block until EOS, error, or signal.

    On SIGINT/SIGTERM this sends EOS rather than tearing down, so splitmuxsink
    finalises the segment being written. Killing the process outright leaves the
    in-progress clip truncated — which is the clip of the set you just did.
    """
    Gst = _gst()

    if missing := missing_elements(spec):
        raise GStreamerUnavailable(
            f"missing GStreamer elements: {', '.join(missing)}"
        )

    pipeline = Gst.parse_launch(spec.description)
    loop_quit_code = 0

    from gi.repository import GLib  # noqa: PLC0415 — same lazy-import boundary

    loop = GLib.MainLoop()

    def on_message(_bus: Any, message: Any) -> bool:
        nonlocal loop_quit_code
        if message.type == Gst.MessageType.EOS:
            log.info("end of stream")
            loop.quit()
        elif message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            log.error("pipeline error: %s (%s)", err, debug)
            loop_quit_code = 1
            loop.quit()
        elif message.type == Gst.MessageType.WARNING:
            warn, _ = message.parse_warning()
            log.warning("pipeline warning: %s", warn)
        return True

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)

    def shutdown(*_args: Any) -> bool:
        log.info("shutting down — flushing current segment")
        pipeline.send_event(Gst.Event.new_eos())
        return True

    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, shutdown)

    if timeout_seconds is not None:
        GLib.timeout_add_seconds(int(timeout_seconds), shutdown)

    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)
    return loop_quit_code
