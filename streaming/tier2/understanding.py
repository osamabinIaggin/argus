"""
Tier 2 — the semantic layer's contract.

Tier 1 answers "what objects are where" (cheap, every frame). Tier 2 answers
"what is *happening*" (expensive, gated) by running a vision-language model on a
single frame plus the current scene context. This module defines the swappable
interface and the result type; concrete backends (FastVLM-MLX, Ollama, a stub)
implement it.

The interface is deliberately model-agnostic — per the pivot rule the model layer
must swap freely between local Apple-Silicon (MLX), a cloud VLM, and a future
CUDA box. Nothing above this line knows which backend is running.

`observe()` is the only required method. The optional `prepare`/`ask` pair is a
seam for image/KV caching (encode one frame once, ask many questions of it) which
matters for the Tier-6 chat/grounding path, not the Tier-2 heartbeat — backends
may leave it unimplemented.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from streaming.frame import Frame


@dataclass(slots=True)
class SceneObservation:
    """One semantic read of a frame."""

    text: str                       # natural-language "what is happening"
    ok: bool = True                 # False if the backend failed (text is the reason)
    infer_ms: float = 0.0
    source: str = "tier2"           # backend / model identifier
    ts_monotonic: Optional[float] = None
    structured: dict = field(default_factory=dict)   # optional parsed fields (future)

    @classmethod
    def failure(cls, reason: str, source: str = "tier2") -> "SceneObservation":
        return cls(text=reason, ok=False, source=source)


class SceneUnderstander(ABC):
    """A swappable 'what is happening' backend."""

    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def observe(self, frame: Frame, context: Optional[str] = None) -> SceneObservation:
        """Describe what is happening in `frame`.

        `context` is a compact text summary of current scene state (entity
        counts, zones, activity) that the backend may fold into its prompt so the
        description is grounded in Tier-1 truth rather than the pixels alone.
        Implementations MUST NOT raise — wrap failures in
        SceneObservation.failure() so a model hiccup degrades gracefully instead
        of taking down the pipeline.
        """
        raise NotImplementedError
