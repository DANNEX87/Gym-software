"""Fixtures are synthetic — see tests/fixtures/README.md."""

from pipeline.controls import framing_controls, needs_change, parse_controls

LISTING = """                     brightness 0x00980900 (int)    : min=-64 max=64 step=1 default=0 value=0
                       contrast 0x00980901 (int)    : min=0 max=100 step=1 default=50 value=50
                   pan_absolute 0x009a0908 (int)    : min=-36000 max=36000 step=3600 default=0 value=7200
                  zoom_absolute 0x009a090d (int)    : min=100 max=400 step=1 default=100 value=250
              face_auto_framing 0x009a0910 (bool)   : default=1 value=1
               speaker_tracking 0x009a0911 (bool)   : default=0 value=0
"""


def test_parses_all_controls():
    assert len(parse_controls(LISTING)) == 6


def test_identifies_reframing_controls_only():
    names = {c.name for c in framing_controls(parse_controls(LISTING))}
    assert names == {"pan_absolute", "zoom_absolute", "face_auto_framing", "speaker_tracking"}
    assert "brightness" not in names


def test_zoom_neutral_is_driver_default_not_zero():
    # Zoom 0 is not a valid 1x; the driver's default is the neutral value.
    zoom = next(c for c in parse_controls(LISTING) if c.name == "zoom_absolute")
    assert zoom.neutral == 100


def test_boolean_framing_neutral_is_off():
    framing = next(c for c in parse_controls(LISTING) if c.name == "face_auto_framing")
    assert framing.neutral == 0


def test_only_reports_controls_actually_off_neutral():
    changing = {c.name for c in needs_change(parse_controls(LISTING))}
    assert changing == {"pan_absolute", "zoom_absolute", "face_auto_framing"}
    # already 0, so nothing to do
    assert "speaker_tracking" not in changing


def test_handles_empty_listing():
    assert parse_controls("") == []
