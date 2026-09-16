"""Rack Vision capture and Phase 1 pipeline.

Import boundary that makes this developable off-target: nothing in this package
imports ``gi``/GStreamer at module level. Pipeline construction is pure — it turns
config plus a detected capture mode into a launch description string — and only
``runtime`` instantiates that description against a real GStreamer.

So the whole decision layer is exercisable on a machine with no camera, no
GStreamer, and no Hailo. See CLAUDE.md, "Build environment vs target".
"""
