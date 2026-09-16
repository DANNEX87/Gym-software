"""The CLI must be fully exercisable off-target, which is the point of --dry-run."""

import pytest

from pipeline.cli import main

MOUNTS_SSD = "/dev/sda1 / ext4 rw 0 0\n"


def dry(capsys, *argv) -> str:
    assert main(["--dry-run", *argv]) == 0
    return capsys.readouterr().out


def test_dry_run_needs_no_camera_and_no_gstreamer(capsys):
    out = dry(capsys, "--source", "test")
    assert "videotestsrc" in out and "splitmuxsink" in out


def test_dry_run_reports_the_resolved_clip_device(capsys):
    assert "clips ->" in dry(capsys, "--source", "test")


def test_auto_source_falls_back_to_synthetic_without_a_device(capsys):
    out = dry(capsys, "--source", "auto", "--device", "/dev/video-does-not-exist")
    assert "videotestsrc" in out


def test_format_override_is_honoured(capsys):
    out = dry(capsys, "--source", "v4l2", "--device", "/dev/video0", "--format", "h264")
    assert "video/x-h264" in out and "v4l2src device=/dev/video0" in out


def test_notes_are_surfaced_to_the_operator(capsys):
    assert "# note:" in dry(capsys, "--source", "test")


def test_sd_card_target_aborts_before_running(tmp_path, monkeypatch, capsys):
    import pipeline.storage as storage

    monkeypatch.setattr(storage, "read_mounts", lambda: "/dev/mmcblk0p2 / ext4 rw 0 0\n")
    with pytest.raises(storage.UnsafeClipTarget, match="SD card"):
        main(["--dry-run", "--source", "test"])


def test_sd_card_override_permits_it(monkeypatch, capsys):
    import pipeline.storage as storage

    monkeypatch.setattr(storage, "read_mounts", lambda: "/dev/mmcblk0p2 / ext4 rw 0 0\n")
    assert main(["--dry-run", "--source", "test", "--allow-sd-card"]) == 0


def test_running_without_gstreamer_gives_an_actionable_error():
    from pipeline.runtime import GStreamerUnavailable

    with pytest.raises(GStreamerUnavailable, match="--dry-run"):
        main(["--source", "test", "--sink", "fake", "--duration", "1"])


def test_missing_v4l2_tooling_reports_cleanly_not_as_a_traceback(capsys):
    from pipeline.cli import run_cli

    # Off-target, probing a real device cannot work. That is an expected
    # operational failure, so it must read as a message, not a stack trace.
    assert run_cli(["--dry-run", "--source", "v4l2", "--device", "/dev/video0"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error:") and "--source test" in err


def test_clean_exit_code_on_sd_card_target(monkeypatch, capsys):
    import pipeline.storage as storage
    from pipeline.cli import run_cli

    monkeypatch.setattr(storage, "read_mounts", lambda: "/dev/mmcblk0p2 / ext4 rw 0 0\n")
    assert run_cli(["--dry-run", "--source", "test"]) == 1
    assert "SD card" in capsys.readouterr().err
