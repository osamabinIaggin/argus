"""
Tier 1 — the always-on, cheap, local detection + tracking layer.

Runs on every frame the consumer pulls (drop-stale ensures it's always the
freshest). Produces objects + persistent track IDs + motion cues with no LLM
cost. This is the system's "peripheral vision": it watches continuously and,
later, triggers the expensive Tier 2 VLM only when something noteworthy happens.
"""

from streaming.tier1.detector import Detector
from streaming.tier1.yolo_detector import YoloDetector

__all__ = ["Detector", "YoloDetector"]
