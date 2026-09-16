"""Build the Phase 1 pipeline description. Pure — no GStreamer import.

Implements design B from docs/PHASE1-DESIGN.md: one always-running graph that
tees capture into a live preview and a rolling segment recorder. The N seconds of
replay live on the SSD, not in a RAM delay line, because at 1080p30 a 10-second
raw delay is ~933 MB against ~15 MB for H.264.

This module only produces a launch description string. Turning that into a running
pipeline is `runtime`'s job. The split is what lets the entire decision layer —
which elements, which caps, which branch — be unit-tested on a machine with no
camera and no GStreamer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .formats import CaptureFormat

NS_PER_SECOND = 1_000_000_000


class Source(Enum):
    V4L2 = "v4l2"
    #: Synthetic frames, for developing off-target. Never used on the Pi.
    TEST = "test"


class Sink(Enum):
    #: Straight to DRM/KMS. Lowest latency, needs console boot (no desktop).
    KMS = "kms"
    WAYLAND = "wayland"
    AUTO = "auto"
    FAKE = "fake"


@dataclass(frozen=True)
class GraphSpec:
    description: str
    notes: tuple[str, ...]

    def __str__(self) -> str:
        return self.description


_SINK_ELEMENTS = {
    Sink.KMS: "kmssink",
    Sink.WAYLAND: "waylandsink fullscreen=true",
    Sink.AUTO: "autovideosink",
    Sink.FAKE: "fakesink sync=true",
}

_CAPS = {
    CaptureFormat.H264: "video/x-h264",
    CaptureFormat.MJPEG: "image/jpeg",
    CaptureFormat.RAW_YUY2: "video/x-raw,format=YUY2",
    CaptureFormat.RAW_NV12: "video/x-raw,format=NV12",
}

_PARSE = {CaptureFormat.H264: "h264parse", CaptureFormat.MJPEG: "jpegparse"}
_DECODE = {CaptureFormat.H264: "avdec_h264", CaptureFormat.MJPEG: "jpegdec"}


def _caps(fmt: CaptureFormat, width: int, height: int, framerate: int) -> str:
    return f"{_CAPS[fmt]},width={width},height={height},framerate={framerate}/1"


def _source_chain(
    source: Source,
    fmt: CaptureFormat,
    device: str | None,
    width: int,
    height: int,
    framerate: int,
) -> list[str]:
    """Elements from the source up to (not including) the parser."""
    caps = _caps(fmt, width, height, framerate)

    if source is Source.V4L2:
        if not device:
            raise ValueError("v4l2 source requires camera.device")
        return [f"v4l2src device={device} io-mode=mmap", caps]

    # Test source produces raw, so a non-raw format has to be synthesised. This
    # exercises the same branch shape off-target without pretending to be a camera.
    raw = f"video/x-raw,format=I420,width={width},height={height},framerate={framerate}/1"
    base = ["videotestsrc pattern=smpte is-live=true", raw]
    if fmt is CaptureFormat.H264:
        return base + [
            f"x264enc speed-preset=ultrafast tune=zerolatency key-int-max={framerate}",
            caps,
        ]
    if fmt is CaptureFormat.MJPEG:
        return base + ["jpegenc", caps]
    return ["videotestsrc pattern=smpte is-live=true", _caps(fmt, width, height, framerate)]


def build(
    *,
    fmt: CaptureFormat,
    clips_dir: str,
    source: Source = Source.V4L2,
    sink: Sink = Sink.KMS,
    device: str | None = None,
    width: int = 1920,
    height: int = 1080,
    framerate: int = 30,
    segment_seconds: int = 10,
    ring_segments: int = 12,
    preview_queue_buffers: int = 8,
) -> GraphSpec:
    """Compose the capture -> tee -> (preview | rolling recorder) graph."""
    if segment_seconds < 1:
        raise ValueError("segment_seconds must be >= 1")
    if ring_segments < 2:
        raise ValueError("ring_segments must be >= 2")

    notes: list[str] = []

    chain = _source_chain(source, fmt, device, width, height, framerate)
    if parse := _PARSE.get(fmt):
        chain.append(parse)
    chain.append("tee name=t")

    # Preview branch. leaky=downstream so a stalled display drops frames instead
    # of back-pressuring capture — the recording must never be damaged by the TV.
    # max-size-bytes/time are zeroed so only the buffer count bounds this queue;
    # left at their defaults they would trip first and the leak would be untuned.
    preview = [
        f"queue leaky=downstream max-size-buffers={preview_queue_buffers} "
        "max-size-bytes=0 max-size-time=0"
    ]
    if decode := _DECODE.get(fmt):
        preview.append(decode)
    preview += ["videoconvert", _SINK_ELEMENTS[sink]]

    # Record branch. Rolling ring of segments on the SSD; max-files makes
    # splitmuxsink drop the oldest rather than filling the disk.
    record = ["queue"]
    if fmt.needs_encode_to_store:
        record += [
            "videoconvert",
            f"x264enc speed-preset=ultrafast tune=zerolatency key-int-max={framerate}",
            "h264parse",
        ]
        notes.append(
            "Raw capture: storing costs a software H.264 encode (~a core at 1080p30) "
            "because the Pi 5 has no hardware encoder. See PHASE1-DESIGN.md §3."
        )
    record.append(
        f"splitmuxsink name=rec location={clips_dir}/set_%05d.mkv "
        f"muxer-factory=matroskamux "
        f"max-size-time={segment_seconds * NS_PER_SECOND} max-files={ring_segments}"
    )

    if fmt is CaptureFormat.H264 and source is Source.V4L2:
        notes.append(
            "Camera-encoded H.264: segments split on keyframes, so the camera's GOP "
            "length is a floor on segment duration. If segments run long, that is the "
            "camera's keyframe interval, not a bug here."
        )
    if fmt is CaptureFormat.MJPEG:
        notes.append(
            "MJPEG stored as-is, not transcoded — spending a core on x264enc to save "
            "SSD space would cost the core Phase 2 needs. See PHASE1-DESIGN.md §3."
        )
    if sink is Sink.KMS:
        notes.append("kmssink needs console boot with no desktop compositor running.")
    if source is Source.TEST:
        notes.append("SYNTHETIC source (videotestsrc) — off-target development only.")

    description = "\n".join(
        [
            " ! ".join(chain),
            "  t. ! " + " ! ".join(preview),
            "  t. ! " + " ! ".join(record),
        ]
    )
    return GraphSpec(description=description, notes=tuple(notes))
