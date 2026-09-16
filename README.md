# Rack Vision

Fixed-camera lifting analysis rig for a home gym.
Raspberry Pi 5 · Insta360 Connect (USB/UVC) · 65" TV on HDMI · Hailo-8 AI HAT+ (later).

## How this project is built

Written in a **cloud container**, deployed to a **Pi 5**. The codebase never assumes it
is on the target: capture format, device nodes, and geometry are config-driven and
runtime-detected, so everything is developable and testable here without hardware.

| | |
|---|---|
| `CLAUDE.md` | Standing constraints. Read first, every session. |
| `docs/PHASE1-DESIGN.md` | Buffering approach for live preview + delayed replay. |
| `config.toml` | Camera geometry + calibration. Filled in at deploy time. |
| `HARDWARE.md` | What the rig actually does. Filled in on the Pi, from a real probe. |
| `scripts/probe-hardware.sh` | Collects the Phase 0 data. Runs on the Pi. |

## On deploy, on the Pi

```bash
sudo ./scripts/probe-hardware.sh          # collect
# transcribe probe-results/<timestamp>/ into HARDWARE.md, then set config.toml
ln -s /mnt/ssd/rack-vision-clips clips    # clips on the SSD, never the SD card
```

The probe answers four things that change runtime behaviour: whether the camera offers
H.264, whether the two lenses are separate nodes, the USB link speed, and whether
auto-framing can be disabled and made to stay disabled.
