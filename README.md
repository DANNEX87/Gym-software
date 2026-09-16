# Rack Vision

Fixed-camera lifting analysis rig for a home gym.
Raspberry Pi 5 · Insta360 Connect (USB/UVC) · 65" TV on HDMI · Hailo-8 AI HAT+ (later).

## Where this is

**Phase 0 — hardware shakeout: not complete.** No probe has been run on the Pi yet.

| | |
|---|---|
| `CLAUDE.md` | Standing constraints. Read first, every session. |
| `HARDWARE.md` | Phase 0 findings — the source of truth. Currently a template. |
| `scripts/probe-hardware.sh` | Run this on the Pi to collect Phase 0 data. |
| `docs/PHASE1-DESIGN.md` | Buffering approach for live preview + delayed replay. |
| `config.toml` | Camera geometry + calibration. Values deliberately unset. |

## Next step — on the Pi

```bash
sudo ./scripts/probe-hardware.sh
```

Then fill in `HARDWARE.md` from `probe-results/<timestamp>/`, pasting raw output into
the appendix. The three questions that decide the architecture, plus the one the
kickoff did not ask, are listed at the end of the probe run.

Nothing in Phase 1 should be built before that is done.

## Setup note

`clips/` must resolve to the USB SSD, not the SD card:

```bash
ln -s /mnt/ssd/rack-vision-clips clips
```
