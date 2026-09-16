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

## Running it

```bash
pip install -e ".[dev]"
pytest                                    # 70 tests, no camera needed

python -m pipeline --dry-run              # print the pipeline it would build
python -m pipeline --dry-run --source v4l2 --device /dev/video0 --format h264
```

`--dry-run` builds the real pipeline description and prints it without needing a
camera, GStreamer, or the Pi. Pipeline construction (`pipeline/graph.py`) is a pure
function of config plus detected capture mode, so every branch is testable here; only
`pipeline/runtime.py` touches GStreamer.

| Module | |
|---|---|
| `pipeline/detect.py` | Parses `v4l2-ctl` output, picks the cheapest capture mode (h264 > mjpeg > raw) |
| `pipeline/graph.py` | Pure: config + mode → pipeline description |
| `pipeline/controls.py` | Finds and neutralises on-device reframing (constraint #1) |
| `pipeline/storage.py` | Refuses to write clips to the SD card (constraint #4) |
| `pipeline/runtime.py` | The only module that imports GStreamer |

## On deploy, on the Pi

```bash
sudo ./scripts/probe-hardware.sh          # collect
# transcribe probe-results/<timestamp>/ into HARDWARE.md, then set config.toml
ln -s /mnt/ssd/rack-vision-clips clips    # clips on the SSD, never the SD card
```

The probe answers four things that change runtime behaviour: whether the camera offers
H.264, whether the two lenses are separate nodes, the USB link speed, and whether
auto-framing can be disabled and made to stay disabled.
