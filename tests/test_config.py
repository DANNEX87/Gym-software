import pytest

from pipeline.config import ConfigError, ConstraintViolation, from_dict


def test_defaults_are_1080p30():
    cfg = from_dict({})
    assert (cfg.camera.width, cfg.camera.height, cfg.camera.framerate) == (1920, 1080, 30)


@pytest.mark.parametrize("key", ["auto_framing", "tracking"])
def test_enabling_reframing_is_rejected(key):
    # CLAUDE.md #1 is permanent, so config cannot switch it back on.
    with pytest.raises(ConstraintViolation, match="CLAUDE.md #1"):
        from_dict({"camera": {key: True}})


@pytest.mark.parametrize("key", ["auto_framing", "tracking"])
def test_explicit_false_is_fine(key):
    assert from_dict({"camera": {key: False}}) is not None


def test_reframing_is_forced_off_even_if_absent():
    cfg = from_dict({})
    assert cfg.camera.auto_framing is False
    assert cfg.camera.tracking is False


def test_geometry_stays_unset_rather_than_defaulting():
    # A plausible-but-wrong calibration constant corrupts metrics silently.
    cfg = from_dict({})
    assert cfg.geometry.height_m is None
    assert not cfg.geometry.calibrated


def test_geometry_calibrated_when_both_measured():
    cfg = from_dict({"geometry": {"height_m": 1.4, "distance_m": 2.7}})
    assert cfg.geometry.calibrated


def test_empty_format_string_means_detect():
    assert from_dict({"camera": {"format": ""}}).camera.format is None


def test_ring_needs_room_to_write_and_replay():
    with pytest.raises(ConfigError, match="ring_segments"):
        from_dict({"replay": {"ring_segments": 1}})


def test_segment_seconds_must_be_positive():
    with pytest.raises(ConfigError, match="segment_seconds"):
        from_dict({"replay": {"segment_seconds": 0}})


def test_malformed_section_is_rejected():
    with pytest.raises(ConfigError, match="must be a table"):
        from_dict({"camera": "not-a-table"})


def test_checked_in_config_loads():
    from pipeline.config import load

    cfg = load("config.toml")
    assert cfg.camera.auto_framing is False
    assert cfg.replay.ring_segments >= 2
