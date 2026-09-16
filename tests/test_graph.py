"""The graph encodes decisions from docs/PHASE1-DESIGN.md. These pin them down."""

import pytest

from pipeline.formats import CaptureFormat
from pipeline.graph import NS_PER_SECOND, GraphSpec, Sink, Source, build


def g(**kw) -> GraphSpec:
    base = dict(fmt=CaptureFormat.H264, device="/dev/video0", clips_dir="/mnt/ssd/clips")
    return build(**{**base, **kw})


def preview_branch(spec: GraphSpec) -> str:
    return [ln for ln in spec.description.splitlines() if ln.strip().startswith("t. !")][0]


def record_branch(spec: GraphSpec) -> str:
    return [ln for ln in spec.description.splitlines() if ln.strip().startswith("t. !")][1]


# --- the core economic decision: who pays for encoding ---------------------

def test_camera_h264_is_never_re_encoded():
    assert "x264enc" not in g(fmt=CaptureFormat.H264).description


def test_mjpeg_is_stored_as_is_not_transcoded():
    # Transcoding to save disk would spend the core Phase 2 needs.
    assert "x264enc" not in g(fmt=CaptureFormat.MJPEG).description


@pytest.mark.parametrize("fmt", [CaptureFormat.RAW_YUY2, CaptureFormat.RAW_NV12])
def test_raw_must_encode_to_store_and_says_so(fmt):
    spec = g(fmt=fmt)
    assert "x264enc" in record_branch(spec)
    assert any("software H.264 encode" in n for n in spec.notes)


def test_raw_encoder_keyframes_allow_requested_segment_length():
    # key-int-max below the segment length, or splitmuxsink cannot split on time.
    assert "key-int-max=30" in g(fmt=CaptureFormat.RAW_YUY2, framerate=30).description


# --- the preview must never damage the recording --------------------------

def test_preview_queue_leaks_downstream():
    assert "leaky=downstream" in preview_branch(g())


def test_record_queue_does_not_leak():
    # Dropping recorded frames would silently corrupt the clip of your set.
    assert "leaky" not in record_branch(g())


def test_preview_queue_bounds_only_by_buffer_count():
    # Left at defaults, max-size-bytes/time would trip before the buffer limit
    # and the leak point would be untuned.
    branch = preview_branch(g())
    assert "max-size-bytes=0" in branch and "max-size-time=0" in branch
    assert "max-size-buffers=8" in branch


# --- rolling recorder -----------------------------------------------------

def test_segment_length_converted_to_nanoseconds():
    assert f"max-size-time={7 * NS_PER_SECOND}" in g(segment_seconds=7).description


def test_ring_depth_caps_files_so_the_ssd_cannot_fill():
    assert "max-files=5" in g(ring_segments=5).description


def test_clips_path_is_used_verbatim():
    assert "location=/mnt/ssd/rv/set_%05d.mkv" in g(clips_dir="/mnt/ssd/rv").description


def test_matroska_survives_an_abrupt_stop():
    assert "muxer-factory=matroskamux" in g().description


# --- structure ------------------------------------------------------------

def test_single_capture_tees_into_exactly_two_branches():
    spec = g()
    assert "tee name=t" in spec.description
    assert spec.description.count("t. !") == 2


@pytest.mark.parametrize(
    "fmt,decoder",
    [(CaptureFormat.H264, "avdec_h264"), (CaptureFormat.MJPEG, "jpegdec")],
)
def test_preview_decodes_compressed_formats(fmt, decoder):
    assert decoder in preview_branch(g(fmt=fmt))


def test_raw_preview_needs_no_decoder():
    branch = preview_branch(g(fmt=CaptureFormat.RAW_YUY2))
    assert "avdec_h264" not in branch and "jpegdec" not in branch


@pytest.mark.parametrize(
    "sink,element",
    [(Sink.KMS, "kmssink"), (Sink.WAYLAND, "waylandsink"), (Sink.AUTO, "autovideosink"), (Sink.FAKE, "fakesink")],
)
def test_sink_selection(sink, element):
    assert element in preview_branch(g(sink=sink))


def test_caps_carry_the_configured_geometry():
    assert "width=1280,height=720,framerate=60/1" in g(width=1280, height=720, framerate=60).description


# --- off-target source ----------------------------------------------------

def test_test_source_never_touches_a_device():
    spec = g(source=Source.TEST, device=None)
    assert "v4l2src" not in spec.description
    assert "videotestsrc" in spec.description


def test_test_source_is_flagged_as_synthetic():
    assert any("SYNTHETIC" in n for n in g(source=Source.TEST, device=None).notes)


def test_test_source_synthesises_compressed_formats():
    # videotestsrc is raw, so exercising the H.264 branch off-target needs an encoder.
    # This is the one legitimate x264enc in an H.264 graph.
    spec = g(source=Source.TEST, device=None, fmt=CaptureFormat.H264)
    assert "x264enc" in spec.description and "h264parse" in spec.description


# --- validation -----------------------------------------------------------

def test_v4l2_without_a_device_is_an_error():
    with pytest.raises(ValueError, match="device"):
        build(fmt=CaptureFormat.H264, clips_dir="/tmp", source=Source.V4L2, device=None)


@pytest.mark.parametrize("kw", [{"segment_seconds": 0}, {"ring_segments": 1}])
def test_invalid_replay_settings_rejected(kw):
    with pytest.raises(ValueError):
        g(**kw)
