import pytest

from pipeline.storage import UnsafeClipTarget, check_clip_target, resolve_target

MOUNTS = """/dev/mmcblk0p2 / ext4 rw,relatime 0 0
/dev/mmcblk0p1 /boot/firmware vfat rw 0 0
/dev/sda1 /mnt/ssd ext4 rw,relatime 0 0
"""


def test_longest_prefix_wins():
    assert resolve_target("/mnt/ssd/clips", MOUNTS).device == "/dev/sda1"
    assert resolve_target("/home/user/clips", MOUNTS).device == "/dev/mmcblk0p2"


def test_sibling_mountpoint_is_not_a_prefix_match():
    # /mnt/ssd2 must not match the /mnt/ssd mount by string prefix.
    assert resolve_target("/mnt/ssd2/clips", MOUNTS).device == "/dev/mmcblk0p2"


def test_sd_card_is_refused():
    with pytest.raises(UnsafeClipTarget, match="SD card"):
        check_clip_target("/home/user/clips", mounts_text=MOUNTS)


def test_ssd_is_allowed():
    assert check_clip_target("/mnt/ssd/clips", mounts_text=MOUNTS).device == "/dev/sda1"


def test_override_is_explicit_and_works():
    target = check_clip_target("/home/user/clips", mounts_text=MOUNTS, allow_sd_card=True)
    assert target.on_sd_card


def test_unknown_backing_device_is_reported_not_guessed():
    target = resolve_target("/anywhere", "")
    assert not target.known and not target.on_sd_card
