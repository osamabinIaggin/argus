"""
Detector — the Tier 1 interface.

Kept abstract so the rest of the pipeline never imports a model directly. Today
the only implementation is YOLO-on-MPS; tomorrow it could be a cloud detector or
a different edge model. Scene state (Tier 3) depends on this interface, not on
ultralytics.
"""

from __future__ import annotations

import abc

from streaming.frame import Frame
from streaming.detection import DetectionResult


class Detector(abc.ABC):
    @abc.abstractmethod
    def detect(self, frame: Frame) -> DetectionResult:
        """Run detection (and tracking, if supported) on a single frame."""
        raise NotImplementedError

    def annotate(self, frame: Frame, result: DetectionResult):
        """
        Optional: return an annotated RGB ndarray for visualization. Default
        implementation is provided by subclasses that can draw efficiently.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support annotate()")

    @property
    def name(self) -> str:
        return type(self).__name__
