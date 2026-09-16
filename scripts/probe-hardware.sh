#!/usr/bin/env bash
#
# Rack Vision — Phase 0 hardware shakeout.
#
# Run this ON THE PI, with the Insta360 Connect plugged in and the TV connected.
#
#     sudo ./scripts/probe-hardware.sh
#
# sudo is not strictly required, but without it lsusb cannot read the full UVC
# descriptors, and those are where the H.264 answer actually lives.
#
# Writes: probe-results/<timestamp>/  — one file per probe, raw output, plus
# summary.txt. Nothing here interprets results; it only collects them.

set -uo pipefail   # deliberately NOT -e: a missing tool must not abort the run

TS="$(date +%Y%m%d-%H%M%S)"
OUT="$(cd "$(dirname "$0")/.." && pwd)/probe-results/${TS}"
mkdir -p "$OUT"
SUMMARY="$OUT/summary.txt"

log()  { echo "$@" | tee -a "$SUMMARY"; }
rule() { log ""; log "=== $* ==="; }

# run <slug> <description> <command...>
# Captures stdout+stderr verbatim to its own file, echoes a one-line verdict.
run() {
  local slug="$1"; shift
  local desc="$1"; shift
  local f="$OUT/${slug}.txt"
  {
    echo "\$ $*"
    echo
    timeout 25 "$@" 2>&1
    echo
    echo "[exit: $?]"
  } > "$f"
  if [ -s "$f" ] && ! grep -qiE 'command not found|No such file' "$f"; then
    log "  [ok]   $desc  -> ${slug}.txt"
  else
    log "  [MISS] $desc  -> ${slug}.txt  (tool missing or no output)"
  fi
}

log "Rack Vision — Phase 0 probe"
log "timestamp: $(date -Is)"
log "output:    $OUT"
log "uid:       $(id -u) $( [ "$(id -u)" -ne 0 ] && echo '(not root — UVC descriptors will be incomplete, re-run with sudo)')"

# ---------------------------------------------------------------- system
rule "System identity"
run model     "Pi model"          bash -c 'tr -d "\0" < /proc/device-tree/model'
run uname     "kernel"            uname -a
run osrelease "OS release"        cat /etc/os-release
run meminfo   "RAM"               bash -c 'head -3 /proc/meminfo'
run firmware  "bootloader/fw"     vcgencmd version
run throttled "throttle flags"    vcgencmd get_throttled
run temp      "SoC temp"          vcgencmd measure_temp

# Power matters here: an under-volting supply shows up as corrupted frames and
# "random" USB dropouts that look exactly like a camera bug.
run psu       "PSU / power state" bash -c 'cat /sys/class/power_supply/*/online 2>/dev/null; dmesg 2>/dev/null | grep -iE "under.?voltage|low voltage" | tail -20'

# ---------------------------------------------------------------- USB
rule "USB bus"
# Topology is not cosmetic. If the Connect enumerates at 480M (USB 2.0) rather
# than 5000M (USB 3.0), raw 1080p30 cannot fit down the wire at all and the
# camera MUST be giving us something compressed. Read the speed next to the device.
run lsusb        "USB devices"        lsusb
run lsusb_tree   "USB topology+speed" lsusb -t
run lsusb_v      "full descriptors"   lsusb -v
run usb_dmesg    "USB enumeration log" bash -c 'dmesg 2>/dev/null | grep -iE "usb|uvc" | tail -60'
run uvc_module   "uvcvideo module"    bash -c 'lsmod | grep -i uvc; modinfo uvcvideo 2>/dev/null | head -5'

# ---------------------------------------------------------------- video
rule "Video devices"
run v4l2_devices "node list"          v4l2-ctl --list-devices

shopt -s nullglob
VIDEO_NODES=(/dev/video*)
shopt -u nullglob

if [ ${#VIDEO_NODES[@]} -eq 0 ]; then
  log "  [FAIL] no /dev/video* nodes exist — camera not enumerated"
else
  log "  found ${#VIDEO_NODES[@]} node(s): ${VIDEO_NODES[*]}"
  for dev in "${VIDEO_NODES[@]}"; do
    n="$(basename "$dev")"
    # The format matrix. This is probe #3 from the kickoff — the one that decides
    # the architecture. Look for H264 / MJPG / YUYV in the output.
    run "fmt_${n}"   "formats  $dev"   v4l2-ctl -d "$dev" --list-formats-ext
    run "all_${n}"   "all info $dev"   v4l2-ctl -d "$dev" --all
    # Controls: this is where on-device auto-framing would be exposed, if it is
    # exposed at all. Grep the result for framing / tracking / zoom / pan / tilt.
    run "ctrl_${n}"  "controls $dev"   v4l2-ctl -d "$dev" --list-ctrls-menus
  done
fi

# ---------------------------------------------------------------- audio
rule "Audio capture"
run arecord_l    "capture cards"      arecord -l
run arecord_L    "PCM devices"        arecord -L
run proc_asound  "asound cards"       bash -c 'cat /proc/asound/cards 2>/dev/null'

# Per-card supported rates/channels. A 14-mic array may present as a high channel
# count device, or may downmix to stereo before the USB boundary.
if command -v arecord >/dev/null 2>&1; then
  while read -r card dev; do
    [ -z "${card:-}" ] && continue
    run "hwparams_hw${card}_${dev}" "hw params hw:${card},${dev}" \
      bash -c "arecord -D hw:${card},${dev} --dump-hw-params -d 1 /dev/null"
  done < <(arecord -l 2>/dev/null | sed -nE 's/^card ([0-9]+):.*device ([0-9]+):.*/\1 \2/p')
fi

# ---------------------------------------------------------------- gstreamer
rule "GStreamer inventory"
run gst_version "version"             gst-launch-1.0 --version
# Confirm what encoders actually exist on this box. On a Pi 5 there is no
# hardware H.264 encoder, so v4l2h264enc is expected to be ABSENT. If x264enc is
# the only H.264 encoder present, software encoding is the only encode path.
for el in v4l2src v4l2h264enc v4l2h264dec x264enc openh264enc avdec_h264 \
          jpegdec v4l2jpegdec kmssink waylandsink glimagesink autovideosink \
          splitmuxsink queue hailonet; do
  if gst-inspect-1.0 "$el" >/dev/null 2>&1; then
    log "  [present] $el"
  else
    log "  [absent ] $el"
  fi
done
run gst_devices "device monitor"      gst-device-monitor-1.0 Video/Source

# ---------------------------------------------------------------- live capture
# Descriptors advertise; hardware delivers. These are not the same thing, and the
# gap between them is the entire reason Phase 0 exists. Try to actually pull
# frames in each format and measure the real framerate.
rule "Live capture tests (advertised vs actual)"
if command -v gst-launch-1.0 >/dev/null 2>&1; then
  for dev in "${VIDEO_NODES[@]}"; do
    n="$(basename "$dev")"
    for caps in \
        "image/jpeg,width=1920,height=1080,framerate=30/1" \
        "video/x-h264,width=1920,height=1080,framerate=30/1" \
        "video/x-raw,format=YUY2,width=1920,height=1080,framerate=30/1" \
        "image/jpeg,width=1280,height=720,framerate=30/1" ; do
      slug="cap_${n}_$(echo "$caps" | tr -c 'a-zA-Z0-9' '_' | cut -c1-40)"
      run "$slug" "capture $dev $caps" \
        gst-launch-1.0 -q v4l2src device="$dev" num-buffers=90 ! "$caps" \
          ! fpsdisplaysink text-overlay=false video-sink=fakesink sync=false
    done
  done
else
  log "  [MISS] gst-launch-1.0 not installed — skipped"
fi

# ---------------------------------------------------------------- storage
rule "Storage"
run blk       "block devices"  lsblk -o NAME,SIZE,TYPE,TRAN,MOUNTPOINT,FSTYPE
run mounts    "mounts"         df -h
run clipsdir  "clips/ target"  bash -c 'ls -ld clips 2>/dev/null; readlink -f clips 2>/dev/null'

rule "Done"
log "Collected $(find "$OUT" -type f | wc -l) files in $OUT"
log ""
log "Next: fill in HARDWARE.md from these files. The three questions that decide"
log "the architecture are:"
log "  1. Does any node list H264 in fmt_video*.txt?     (encode cost)"
log "  2. Do wide and tele appear as separate nodes?      (which node we use)"
log "  3. Does lsusb -t show the bar at 5000M or 480M?    (bandwidth ceiling)"
log "And the one the kickoff did not ask but must be answered:"
log "  4. Does ctrl_video*.txt expose auto-framing, and can it be turned OFF?"
