"""Parsing and mode selection. Fixtures are synthetic — see tests/fixtures/README.md."""

import pytest

from pipeline.detect import Mode, StepwiseOnly, parse_formats, select_mode
from pipeline.formats import CaptureFormat

MIXED = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\t\tInterval: Discrete 0.067s (15.000 fps)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.017s (60.000 fps)
\t[1]: 'H264' (H.264, compressed)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[2]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
"""


def test_parses_every_format_and_size():
    modes = parse_formats(MIXED)
    assert len(modes) == 4
    assert {m.fourcc for m in modes} == {"MJPG", "H264", "YUYV"}


def test_collects_multiple_framerates():
    mode = next(m for m in parse_formats(MIXED) if m.fourcc == "MJPG" and m.width == 1920)
    assert mode.framerates == (30.0, 15.0)
    assert mode.supports(30) and mode.supports(15)
    assert not mode.supports(60)


def test_unknown_fourcc_is_skipped():
    text = "\t[0]: 'XXXX' (mystery)\n\t\tSize: Discrete 640x480\n"
    assert parse_formats(text) == []


def test_h264_wins_over_mjpeg_at_same_geometry():
    # Both offer 1920x1080@30; H.264 costs no encode, so it must be preferred.
    chosen = select_mode(parse_formats(MIXED), 1920, 1080, 30)
    assert chosen is not None and chosen.fmt is CaptureFormat.H264


def test_falls_back_to_mjpeg_when_no_h264():
    modes = [m for m in parse_formats(MIXED) if m.fourcc != "H264"]
    chosen = select_mode(modes, 1920, 1080, 30)
    assert chosen is not None and chosen.fmt is CaptureFormat.MJPEG


def test_no_match_returns_none_rather_than_a_different_geometry():
    # Silently substituting 720p would change the frame coordinate system.
    assert select_mode(parse_formats(MIXED), 1920, 1080, 60) is None
    assert select_mode(parse_formats(MIXED), 3840, 2160, 30) is None


def test_stepwise_only_raises_rather_than_looking_empty():
    text = "\t[0]: 'YUYV' (YUYV 4:2:2)\n\t\tSize: Stepwise 32x32 - 1920x1080 with step 2/2\n"
    with pytest.raises(StepwiseOnly):
        parse_formats(text)


def test_supports_tolerates_ntsc_rates():
    assert Mode(CaptureFormat.H264, "H264", 1920, 1080, (29.97,)).supports(30)
