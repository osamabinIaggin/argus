"""
YoloDetector — Tier 1 detection + tracking via Ultralytics YOLO on Apple Silicon.

Uses model.track(persist=True) so each object keeps a stable track_id across
frames (ByteTrack by default). Runs on the MPS (Metal) backend on Apple Silicon,
falling back to CPU with a warning if MPS is unavailable.

Default weights are YOLO26-nano (NMS-free, end-to-end) — verified on MPS at
~30fps / 12-18ms per frame with stable ByteTrack ids. The model is fully
swappable via model_path: yolov8n.pt (the offline-committed fallback), yolo11n.pt,
or a larger yolo26{s,m,l}.pt all work unchanged. The MLX-native yolo-mlx backend
(1.1-2.6x faster than PyTorch-MPS) is a future Detector subclass, not this one.

Heavy imports (torch, ultralytics) are deferred to first use so importing this
module — and the Tier 1 interface — stays cheap and does not explode if the ML
stack isn't installed yet.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import numpy as np

from streaming.frame import Frame
from streaming.detection import Detection, DetectionResult
from streaming.tier1.detector import Detector

logger = logging.getLogger(__name__)


class YoloDetector(Detector):
    def __init__(
        self,
        model_path: str = "yolo26n.pt",
        *,
        device: str = "mps",
        conf: float = 0.25,
        imgsz: int = 640,
        tracker: str = "bytetrack.yaml",
        classes: Optional[List[int]] = None,
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._conf = conf
        self._imgsz = imgsz
        self._tracker = tracker
        self._classes = classes
        self._model = None          # lazy
        self._names: dict[int, str] = {}
        self._last_raw = None        # last ultralytics Results, for annotate()

    # -- lazy model load ---------------------------------------------------

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        import torch
        from ultralytics import YOLO

        if self._device == "mps" and not torch.backends.mps.is_available():
            logger.warning("MPS not available — falling back to CPU")
            self._device = "cpu"

        logger.info("loading YOLO model %s on %s", self._model_path, self._device)
        self._model = YOLO(self._model_path)
        self._names = self._model.names
        self._model.to(self._device)

    # -- Detector contract -------------------------------------------------

    def detect(self, frame: Frame) -> DetectionResult:
        self._ensure_model()

        # Ultralytics treats numpy input as BGR (OpenCV convention); our frames
        # are canonical RGB, so flip channels. ascontiguousarray because the
        # negative-stride view from [..., ::-1] is not contiguous.
        bgr = np.ascontiguousarray(frame.data[:, :, ::-1])

        t0 = time.monotonic()
        results = self._model.track(
            bgr,
            persist=True,            # keep track IDs across consecutive frames
            tracker=self._tracker,
            device=self._device,
            conf=self._conf,
            imgsz=self._imgsz,
            classes=self._classes,
            verbose=False,
        )
        infer_ms = (time.monotonic() - t0) * 1000.0

        r = results[0]
        self._last_raw = r

        detections: List[Detection] = []
        boxes = getattr(r, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            clss = boxes.cls.cpu().numpy().astype(int)
            ids = (
                boxes.id.cpu().numpy().astype(int)
                if getattr(boxes, "id", None) is not None
                else [None] * len(xyxy)
            )
            for (x1, y1, x2, y2), cf, cl, tid in zip(xyxy, confs, clss, ids):
                detections.append(
                    Detection(
                        label=self._names.get(int(cl), str(int(cl))),
                        confidence=float(cf),
                        bbox=(float(x1), float(y1), float(x2), float(y2)),
                        class_id=int(cl),
                        track_id=int(tid) if tid is not None else None,
                    )
                )

        return DetectionResult(
            source_id=frame.source_id,
            frame_seq=frame.seq,
            ts_monotonic=frame.ts_monotonic,
            detections=detections,
            infer_ms=infer_ms,
            frame_width=frame.width,
            frame_height=frame.height,
        )

    def annotate(self, frame: Frame, result: DetectionResult) -> np.ndarray:
        """Return an RGB ndarray with boxes/labels/track-ids drawn (via YOLO's plotter)."""
        if self._last_raw is None:
            return frame.data
        annotated_bgr = self._last_raw.plot()      # BGR ndarray
        return np.ascontiguousarray(annotated_bgr[:, :, ::-1])
