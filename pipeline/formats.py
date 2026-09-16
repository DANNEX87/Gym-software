"""Capture formats and the preference order between them.

The ordering is not arbitrary. The Pi 5 has no hardware video encoder, so the
format the camera hands us decides how much CPU recording costs — which is CPU
Phase 2 inference needs. See docs/PHASE1-DESIGN.md §3.
"""

from __future__ import annotations

from enum import Enum


class CaptureFormat(Enum):
    """A capture format, ordered best-to-worst by what it costs us."""

    #: Camera encodes. Recording is a mux, no encode at all. Best case.
    H264 = "h264"
    #: Cheap decode for preview; store as-is rather than transcoding.
    MJPEG = "mjpeg"
    #: Uncompressed. Storage requires software encode. Worst case.
    RAW_YUY2 = "yuy2"
    RAW_NV12 = "nv12"

    @property
    def is_raw(self) -> bool:
        return self in (CaptureFormat.RAW_YUY2, CaptureFormat.RAW_NV12)

    @property
    def needs_encode_to_store(self) -> bool:
        """True if recording this format costs a software encode (~a core at 1080p30)."""
        return self.is_raw


#: Best first. `select_mode` walks this order.
PREFERENCE: tuple[CaptureFormat, ...] = (
    CaptureFormat.H264,
    CaptureFormat.MJPEG,
    CaptureFormat.RAW_NV12,
    CaptureFormat.RAW_YUY2,
)

#: V4L2 fourcc -> format. AVC1 and H264 both appear on UVC devices.
_FOURCC = {
    "H264": CaptureFormat.H264,
    "AVC1": CaptureFormat.H264,
    "MJPG": CaptureFormat.MJPEG,
    "JPEG": CaptureFormat.MJPEG,
    "YUYV": CaptureFormat.RAW_YUY2,
    "NV12": CaptureFormat.RAW_NV12,
}


def from_fourcc(fourcc: str) -> CaptureFormat | None:
    """Map a V4L2 fourcc to a format, or None if we do not handle it."""
    return _FOURCC.get(fourcc.strip().upper())
