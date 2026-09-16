# HARDWARE.md — Phase 0 findings

> ## STATUS: awaiting probe — values are filled in at deploy time
>
> This file is the **source of truth for what the rig actually does**, and it gets
> written on the Pi, not in the cloud container the codebase is developed in.
>
> Every measured cell reads `UNVERIFIED` because no probe has run yet. Those rows mark
> **what the code must not assume** — they are not blocked work. Code targeting any of
> them should detect at runtime or read `config.toml`.
>
> **To fill this in:** run `sudo ./scripts/probe-hardware.sh` on the Pi with the Connect
> plugged in, then transcribe from `probe-results/<timestamp>/`, pasting raw output into
> the appendix. Per `CLAUDE.md` #5: measured values only, never inferred ones.

Rig: Raspberry Pi 5 · Insta360 Connect (USB/UVC) · 65" TV on HDMI · Hailo-8 AI HAT+ (not yet installed)

---

## 1. The question that decides the architecture

**Can the camera hand us an already-encoded H.264 stream?**

The Pi 5 has **no hardware video encoder** — Broadcom dropped the H.264 encode block
that the Pi 4 had. So this is a fork in the road, not a detail:

| Answer | Consequence |
|---|---|
| **Yes, H.264 over UVC** | Recording costs ~nothing. Mux the camera's bitstream straight to disk. Full CPU stays free for Phase 2 inference. |
| **No, MJPEG only** | Decode JPEG (cheap) but any stored H.264 needs `x264enc` in software — roughly a core at 1080p30. That core is one we want for Hailo pre/post-processing. Alternative: store MJPEG and accept ~5–10× the file size on the SSD. |
| **No, YUYV only** | Worst case. Raw 1080p30 is ~93 MB/s over the wire, which does not fit USB 2.0 at all, and software encode becomes mandatory. |

| Finding | Value |
|---|---|
| H.264 offered over UVC? | `UNVERIFIED` |
| MJPEG offered? | `UNVERIFIED` |
| Raw (YUYV/NV12) offered? | `UNVERIFIED` |
| Source | `probe-results/*/fmt_video*.txt` |

---

## 2. Video devices

| Node | Belongs to | Which lens | Formats | Max res @ fps | Notes |
|---|---|---|---|---|---|
| `/dev/videoN` | `UNVERIFIED` | `UNVERIFIED` | `UNVERIFIED` | `UNVERIFIED` | |

A UVC camera commonly claims several `/dev/video*` nodes where only some are
capture nodes; the rest are metadata nodes. Record which is which.

| Finding | Value |
|---|---|
| Total `/dev/video*` nodes | `UNVERIFIED` |
| Nodes that actually capture | `UNVERIFIED` |
| **Wide and tele as separate nodes?** | `UNVERIFIED` |
| If not separate, how is lens selected? | `UNVERIFIED` |
| USB link speed (`5000M` vs `480M`) | `UNVERIFIED` |

The link speed is not trivia. `480M` is a 60 MB/s theoretical ceiling and appreciably
less in practice, against the ~93 MB/s that raw 1080p30 needs — which would mean the camera
*must* be compressing, and would also cap what we can pull from two lenses at once.

### Format matrix

Per node, transcribe the full `--list-formats-ext` output:

| Node | Pixel format | Resolution | Framerates |
|---|---|---|---|
| | `UNVERIFIED` | | |

### Advertised vs actually delivered

Descriptors advertise; hardware delivers. The probe tries a real 90-frame capture
in each format and measures true fps.

| Node | Caps attempted | Negotiated? | Measured fps | Source |
|---|---|---|---|---|
| | `UNVERIFIED` | | | `cap_video*.txt` |

---

## 3. Auto-framing — the constraint risk ⚠

**The kickoff did not ask this. It is the most dangerous unknown in the build.**

The Insta360 Connect is sold as a smart video bar; auto-framing and speaker tracking
are its headline features, and it has two lenses precisely so it can switch between
a wide shot and a tight one. Both behaviours are *on-device*, upstream of the USB
boundary.

That directly threatens constraint #1 in `CLAUDE.md`. If the camera digitally pans,
crops, or switches lens mid-set, it is functionally a moving camera — bar path and
depth become unmeasurable, and they do so **silently**, producing plausible-looking
numbers that are wrong. A gimbal that physically moves would at least be obvious.

Phase 0 must answer:

| Question | Value |
|---|---|
| Does the device auto-frame on the USB stream by default? | `UNVERIFIED` |
| Is auto-framing exposed as a V4L2 control? | `UNVERIFIED` |
| **Can it be disabled, and does the setting persist across power cycles?** | `UNVERIFIED` |
| Can the lens be locked to one fixed FOV? | `UNVERIFIED` |
| Does disabling require the vendor app / a mode the Pi cannot set? | `UNVERIFIED` |
| Source | `probe-results/*/ctrl_video*.txt` |

**How to test it properly:** controls are not proof. Frame the empty rack, start a
capture, then walk into frame and move laterally. If the framing shifts at all, the
device is reframing. Repeat after a power cycle to confirm the setting sticks.

If auto-framing cannot be disabled and made to persist, that is a hardware blocker,
not a software problem — escalate before writing any Phase 1 code.

---

## 4. Audio — 14-mic array

| Finding | Value |
|---|---|
| Appears as a capture device? | `UNVERIFIED` |
| Card / device id | `UNVERIFIED` |
| Channel count (14 discrete, or downmixed?) | `UNVERIFIED` |
| Sample rates | `UNVERIFIED` |
| Formats | `UNVERIFIED` |
| Source | `arecord_l.txt`, `hwparams_*.txt` |

Audio is not on the critical path for lifting analysis, but a rep-timing or
bar-drop cue from audio is cheap if the array exposes discrete channels.

---

## 5. Encode / decode inventory on the Pi

| Element | Present? | Meaning |
|---|---|---|
| `v4l2h264enc` | `UNVERIFIED` — **expected ABSENT** | Pi 5 has no hardware H.264 encoder |
| `x264enc` | `UNVERIFIED` | software encode; costs ~a core at 1080p30 |
| `avdec_h264` | `UNVERIFIED` | software decode |
| `jpegdec` | `UNVERIFIED` | MJPEG decode |
| `kmssink` | `UNVERIFIED` | direct-to-HDMI, no compositor — preferred sink |
| `hailonet` | `UNVERIFIED` — expected absent until HAT+ arrives | Phase 2 |

---

## 6. System

| Finding | Value |
|---|---|
| Pi model string | `UNVERIFIED` |
| RAM | `UNVERIFIED` |
| OS / kernel | `UNVERIFIED` |
| Throttling flags at idle | `UNVERIFIED` |
| Under-voltage in dmesg? | `UNVERIFIED` |
| SSD present, size, `TRAN` | `UNVERIFIED` |
| `clips/` resolves to SSD? | `UNVERIFIED` |

Under-voltage deserves attention: an undersized supply presents as corrupted frames
and USB dropouts that are easy to misdiagnose as a camera fault.

---

## 7. Commands

Exactly what `scripts/probe-hardware.sh` runs. The kickoff's four commands are the
core; the rest close gaps that would otherwise bite later.

```bash
# --- from the kickoff ---
v4l2-ctl --list-devices                      # which nodes, and are both lenses separate?
v4l2-ctl -d /dev/video0 --list-formats-ext   # THE ONE: H.264, or only MJPEG/YUYV?
arecord -l                                   # does the 14-mic array appear?
ffplay -f v4l2 -framerate 30 -video_size 1920x1080 -i /dev/video0   # live view

# --- added, and why ---
lsusb -t                        # link speed: 5000M vs 480M caps everything downstream
lsusb -v                        # full UVC descriptors — where H.264 support really shows
v4l2-ctl -d /dev/videoN --list-ctrls-menus   # is auto-framing exposed and disableable?
v4l2-ctl -d /dev/videoN --all                # current negotiated state
vcgencmd get_throttled                       # power/thermal problems masquerading as camera bugs
gst-inspect-1.0 v4l2h264enc                  # confirm the encoder really is absent
gst-launch-1.0 v4l2src num-buffers=90 ! <caps> ! fpsdisplaysink   # advertised vs actual
lsblk -o NAME,SIZE,TYPE,TRAN,MOUNTPOINT      # confirm clips land on the SSD
```

---

## 8. Appendix — raw output

> Paste verbatim from `probe-results/<timestamp>/`. Do not summarise; the raw text is
> the evidence, and a future session will want to re-read it rather than trust a gloss.

### `v4l2-ctl --list-devices`
```
UNVERIFIED — not yet run on the Pi
```

### `v4l2-ctl -d /dev/video0 --list-formats-ext`
```
UNVERIFIED — not yet run on the Pi
```

### `lsusb -t`
```
UNVERIFIED — not yet run on the Pi
```

### `v4l2-ctl -d /dev/video0 --list-ctrls-menus`
```
UNVERIFIED — not yet run on the Pi
```

### `arecord -l`
```
UNVERIFIED — not yet run on the Pi
```
