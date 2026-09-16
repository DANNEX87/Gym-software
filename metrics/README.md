# metrics/

Depth, bar path, tempo. Pure functions over pose keypoints — no I/O, no capture,
no display. Everything here must be unit-testable without a camera attached.

All metrics are frame-relative, which is why the camera must never move
(`CLAUDE.md` #1).
