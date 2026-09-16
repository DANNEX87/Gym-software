# Phase 1 — live preview + delayed replay: buffering approach

**Status: proposal only. No pipeline code written.** Per the kickoff, the buffering
approach gets explained and agreed before anything is built. It is also genuinely
blocked: the right pipeline depends on the H.264 answer from Phase 0, which has not
been measured yet.

Goal: full-screen live preview on the TV, plus a configurable N-second replay loop, so
you can finish a set, turn around, and watch it.

---

## 1. The number that decides the design

Everything follows from how much a delay line costs in RAM. A delay of N seconds means
N seconds of video held in memory, so the only question that matters is *how big is a
second of video at this point in the pipeline*.

At 1080p30:

| Held as | Per second | 5 s | 10 s | 30 s |
|---|---|---|---|---|
| Raw NV12 (1920×1080×1.5 = 2.97 MiB/frame) | 93 MB/s | 466 MB | **933 MB** | 2.8 GB |
| Raw YUY2 (4 MiB/frame) | 124 MB/s | 622 MB | 1.24 GB | 3.7 GB |
| MJPEG (~250 KB/frame, quality-dependent) | ~7.5 MB/s | 37 MB | **75 MB** | 225 MB |
| H.264 @ 12 Mbit/s | 1.5 MB/s | 7.5 MB | **15 MB** | 45 MB |

A 10-second raw delay is roughly a gigabyte. On a Pi 5 that is survivable on the 8 GB
model and hostile on the 4 GB, and in both cases it is memory we want for Hailo in
Phase 2. The same delay on the compressed stream is 15–75 MB — between 12× and 60×
cheaper.

**So: delay the compressed stream, always. Decode late, as close to the sink as
possible.** Every design below is a consequence of that one rule.

---

## 2. Three ways to build it

### A. True delay line — `queue` with `min-threshold-time`

A `queue` that refuses to emit until it has accumulated N seconds becomes a delay line.
It is the most direct reading of "N-second delay".

The mechanics matter, because a `queue` has three independent limits and trips on
whichever it hits first. For a time-based delay the other two must be disabled:

```
queue  min-threshold-time = N × 1e9    # start emitting only after N seconds buffered
       max-size-time      > N × 1e9    # must exceed the threshold or it deadlocks
       max-size-buffers   = 0          # disabled
       max-size-bytes     = 0          # disabled
```

Leave `max-size-bytes` at its 10 MB default and a 30-second H.264 delay silently
truncates; leave `max-size-buffers` at 200 and you get 6.6 seconds regardless of what
you asked for.

**The catch:** to show live *and* delayed you need both branches decoded, and the Pi 5
has no hardware H.264 decoder either — decode is software both times. You can avoid the
double decode by putting an `input-selector` *before* a single decoder and switching
between branches, but you cannot join an H.264 stream at an arbitrary frame: the
decoder needs an IDR, so switching stalls until the next keyframe. With a camera-side
encoder you do not control the GOP length, so that stall could be seconds. This is
worth measuring rather than assuming, but it makes A less attractive than it first looks.

### B. Rolling segment recorder + on-demand replay — **recommended**

Two decoupled pipelines instead of one clever one.

```
Recorder (always running):
  v4l2src → tee ┬→ queue(leaky=downstream) → decode → kmssink      [live preview]
                └→ queue → h264parse → splitmuxsink                 [rolling clips → SSD]
                           splitmuxsink max-size-time = N seconds
                                        max-files    = ring depth

Player (on demand):
  filesrc (most recent segment) → decode → kmssink, looped
```

Why this wins for the actual use case:

- **No delay line at all.** The N seconds live on the SSD, not in RAM. Memory cost is a
  couple of small queues.
- **The preview branch is `leaky=downstream`**, so if the display stalls it drops frames
  rather than back-pressuring the recorder. The recording — the thing you actually care
  about — is never damaged by a hiccup on the TV.
- **You get clips on the SSD for free**, which Phase 2 pose analysis needs anyway. Design
  A produces nothing durable.
- **It matches what you actually asked for.** "Finish a set, turn around, watch it" wants
  *the whole set*, not a rolling window that started mid-rep. A segment is a set.

The trade: replay is chunked to segment boundaries rather than continuously rolling. A
set that straddles two segments needs the player to concatenate the last two — which is
a playlist detail, not an architectural problem.

### C. Continuous raw delay

Only viable with the resolution and framerate cut hard enough that the table in §1 comes
down to something sane — 720p15 NV12 is 20 MB/s, so 10 seconds is 200 MB. Listed for
completeness. Not recommended: it spends the memory budget on the preview path, which is
the least valuable thing in the system, and it degrades the image you are trying to
analyse.

**Recommendation: B**, with A available as a variant if you decide you want a true
continuous mirror-with-delay rather than set-at-a-time replay. B is the one that also
feeds Phase 2.

---

## 3. What changes based on the Phase 0 answer

### If the camera delivers H.264

The good case. `v4l2src → h264parse → splitmuxsink` records with **no encode at all** —
we are muxing a bitstream the camera already produced. Preview costs one software
decode. Both cores we want for Hailo stay free.

### If the camera delivers MJPEG only

**Do not reach for `x264enc`.** The instinct is to transcode to H.264 for storage, and it
is the wrong call: software-encoding 1080p30 costs roughly a core, which is precisely the
core Phase 2 needs — you would be spending inference budget to save disk on a machine
with a 500 GB SSD.

Store the MJPEG instead. At ~7.5 MB/s that is ~27 GB/hour, and with a ring buffer you are
only ever holding the recent window plus whatever sets you explicitly keep. Disk is the
cheap resource here; CPU is not. Preview is `jpegdec`, which is much cheaper than H.264
decode anyway.

Revisit only if the SSD genuinely fills, and even then the fix is a shorter ring or
batch-transcoding *after* the session, when nothing is competing for CPU.

### If the camera delivers raw YUYV only

At 124 MB/s this cannot cross USB 2.0, so this case only exists if the bar enumerates at
5 Gbit/s. Storage then requires encoding, and the `x264enc` cost becomes unavoidable —
at which point dropping to 1080p at a lower framerate, or accepting that recording and
inference cannot run simultaneously, becomes a real architectural constraint. Phase 2
would need rethinking. Hope for anything but this.

---

## 4. Display sink

`kmssink` writing straight to DRM/KMS, with the Pi booted to console and no desktop.
No compositor in the path, lowest latency, least CPU. If you keep the desktop, it is
`waylandsink` fullscreen under labwc on Bookworm, which costs a compositor pass.

For a rig whose only job is to show one video full-screen on one TV, the desktop earns
nothing. Recommend console boot.

---

## 5. Open questions Phase 0 must settle first

1. **H.264 over UVC — yes or no?** Decides §3 entirely.
2. **Is auto-framing off, and does it stay off?** See `HARDWARE.md` §3. If the camera
   reframes on its own, Phase 1 is still buildable but every Phase 2 measurement is
   corrupt. This is the one that could invalidate the hardware choice, so it is worth
   answering early even though it is a Phase 2 concern.
3. **Wide or tele, and can the lens be locked?** A lens switch mid-set changes the
   intrinsics and breaks calibration in `config.toml`.
4. **USB 5000M or 480M?** Sets the bandwidth ceiling for everything above.
5. **Actual sustained framerate**, not the advertised one — the probe's capture test
   measures this. A camera that claims 30 and delivers 24 under sustained load changes
   the tempo maths.
