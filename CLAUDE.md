# Rack Vision — standing constraints

Fixed-camera lifting analysis rig. Raspberry Pi 5 + Insta360 Connect (USB/UVC) + 65" TV on HDMI.
Hailo-8 AI HAT+ arrives later.

These constraints are permanent. They are not preferences to be re-litigated per session.

## 1. The camera is FIXED

Subject tracking stays **off, permanently**. Never add pan/tilt. Never enable auto-framing,
speaker tracking, or any "smart" reframing the camera offers.

The reason is not aesthetic. Every measurement this project produces — bar path, depth,
tempo — is **relative to the frame**. A camera that moves, digitally crops, or switches
lenses mid-set destroys the coordinate system those measurements live in, silently. The
data does not look wrong. It just is wrong.

This extends to the camera's own on-device behaviour: if the Connect reframes internally
before the USB stream, that is the same failure as a motorised gimbal. See
`HARDWARE.md` § Auto-framing.

## 2. GStreamer, not OpenCV, for the video path

The Hailo pose pipeline is GStreamer-native and lands in Phase 2. Keep frames inside
GStreamer. OpenCV is acceptable for offline analysis of already-written clips and for
pure-function metric work; it must not own the capture or display path.

## 3. Everything runs offline on the Pi

No cloud inference. No uploading clips for processing. No runtime dependency on a network.

## 4. Clips go on the USB SSD, never the SD card

Sustained video writes kill SD cards. `clips/` must resolve to the SSD (symlink or mount).
Never let a recording path default to the SD card.

## 5. Do not fabricate hardware facts

`HARDWARE.md` is the source of truth for what this rig can actually do, and every value in
it must come from a command that was actually run on the Pi, with its raw output attached.
Rows marked `UNVERIFIED` are not yet known. Do not fill them in from datasheets, vendor
marketing, or inference — probe, or leave them blank.

## Phase status

- **Phase 0 — hardware shakeout: NOT COMPLETE.** `HARDWARE.md` is a template. No probe has
  been run on the Pi yet. Run `scripts/probe-hardware.sh` on the Pi first.
- Phase 1 — live preview + delayed replay on the TV. Design in `docs/PHASE1-DESIGN.md`.
  Blocked on Phase 0, because the pipeline shape depends on whether the camera can hand us
  an already-encoded H.264 stream.
- Phase 2 — Hailo pose inference. Blocked on the AI HAT+ arriving.

Do not write application code ahead of the phase it belongs to.
