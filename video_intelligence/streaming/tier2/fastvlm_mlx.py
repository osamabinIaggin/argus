"""
FastVLMUnderstander — Tier 2 backed by Apple FastVLM on MLX (Apple Silicon).

FastVLM is currently the fastest on-device VLM for real-time use (its hybrid
vision encoder gives a far lower time-to-first-token than comparable models),
which is exactly what a gated ~1fps semantic tier wants on an M-series Mac.

Heavy deps (mlx, mlx_vlm, PIL) are imported lazily on first observe(), so this
module — and the Tier-2 interface — stays importable on any machine and the test
suite runs against the stub without MLX present.

Install on device:  ./.venv/bin/pip install mlx-vlm pillow timm
  (timm + torch are pulled in by FastVLM's custom processor code; torch is
  already present from Tier 1.)
Default weights:     mlx-community/FastVLM-0.5B-bf16

Two robustness measures, both learned the hard way validating this on an M3:

  1. Real-file download. FastVLM ships custom architecture code (llava_qwen.py)
     loaded via transformers' trust_remote_code. transformers 5.x resolves a
     custom module's *relative imports* against the realpath of the file, which
     in the standard HF cache is the hash-named blobs/ dir — so it looks for
     `blobs/llava_qwen.py`, which does not exist, and load() fails with
     FileNotFoundError. We sidestep it by snapshot_download()-ing to a real-file
     local dir (no symlinks), where sibling .py files resolve correctly.
  2. generate() drift. mlx-vlm's generate() signature and return type vary across
     releases (positional image vs prompt order; str vs result-object return).
     We probe the working call once and normalize the output.

observe() never raises — failures come back as SceneObservation.failure so the
pipeline degrades to "semantic stale" instead of crashing.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from streaming.frame import Frame
from streaming.tier2.understanding import SceneObservation, SceneUnderstander

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "mlx-community/FastVLM-0.5B-bf16"
_DEFAULT_PROMPT = (
    "You are a live camera analyst. In one or two sentences, describe what is "
    "happening in this scene right now — the people/objects and their actions. "
    "Be concrete and concise."
)


class FastVLMUnderstander(SceneUnderstander):
    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL,
        *,
        prompt: str = _DEFAULT_PROMPT,
        max_tokens: int = 80,
        local_dir: Optional[str] = None,
    ) -> None:
        self._model_path = model_path
        self._prompt = prompt
        self._max_tokens = max_tokens
        # Where to materialize a real-file copy (see module docstring #1). Default
        # keeps it out of the project tree, next to other app caches.
        self._local_dir = local_dir or os.path.expanduser(
            f"~/.cache/argus/models/{Path(model_path).name}"
        )
        self._resolved_path: Optional[str] = None
        self._model = None
        self._processor = None
        self._config = None

    @property
    def name(self) -> str:
        return f"fastvlm:{self._model_path}"

    # -- model resolution --------------------------------------------------
    def _resolve_path(self) -> str:
        """Return a real-file local dir for the model (downloading if needed)."""
        if self._resolved_path is not None:
            return self._resolved_path
        # Already a local directory? Use it as-is.
        if os.path.isdir(self._model_path):
            self._resolved_path = self._model_path
            return self._resolved_path
        from huggingface_hub import snapshot_download  # type: ignore

        # local_dir gives real files (not blob symlinks) — the transformers
        # relative-import resolver then finds sibling .py files correctly.
        logger.info("materializing %s → %s", self._model_path, self._local_dir)
        self._resolved_path = snapshot_download(
            repo_id=self._model_path, local_dir=self._local_dir
        )
        return self._resolved_path

    # -- lazy load ---------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from mlx_vlm import load  # type: ignore
        from mlx_vlm.utils import load_config  # type: ignore

        path = self._resolve_path()
        logger.info("loading FastVLM from %s via MLX…", path)
        self._model, self._processor = load(path)
        try:
            self._config = load_config(path)
        except Exception:  # noqa: BLE001 — config is optional for the chat template
            self._config = None

    def _build_prompt(self, context: Optional[str]) -> str:
        text = self._prompt
        if context:
            text += f"\n\nDetector context (ground truth): {context}"
        # apply_chat_template formats it for the specific model; fall back to raw.
        try:
            from mlx_vlm.prompt_utils import apply_chat_template  # type: ignore

            return apply_chat_template(self._processor, self._config, text, num_images=1)
        except Exception:  # noqa: BLE001
            return text

    def _generate(self, image, formatted_prompt: str) -> str:
        """Call mlx_vlm.generate across known signature variants, return text."""
        from mlx_vlm import generate  # type: ignore

        # Try the call orderings seen across mlx-vlm releases, newest first.
        attempts = (
            lambda: generate(self._model, self._processor, formatted_prompt, [image],
                             max_tokens=self._max_tokens, verbose=False),
            lambda: generate(self._model, self._processor, [image], formatted_prompt,
                             max_tokens=self._max_tokens, verbose=False),
            lambda: generate(self._model, self._processor, formatted_prompt, image,
                             max_tokens=self._max_tokens, verbose=False),
        )
        last_err: Optional[Exception] = None
        for call in attempts:
            try:
                out = call()
                return _result_text(out)
            except TypeError as exc:       # wrong signature — try the next ordering
                last_err = exc
                continue
        raise last_err if last_err else RuntimeError("mlx_vlm.generate failed")

    # -- SceneUnderstander -------------------------------------------------
    def observe(self, frame: Frame, context: Optional[str] = None) -> SceneObservation:
        t0 = time.monotonic()
        try:
            self._ensure_loaded()
            from PIL import Image  # type: ignore

            # Frame is canonical RGB uint8 — PIL wants exactly that.
            image = Image.fromarray(np.ascontiguousarray(frame.data))
            formatted = self._build_prompt(context)
            text = self._generate(image, formatted).strip()
            return SceneObservation(
                text=text,
                source=self.name,
                infer_ms=(time.monotonic() - t0) * 1000.0,
                ts_monotonic=frame.ts_monotonic,
            )
        except Exception as exc:  # noqa: BLE001 — never take down the pipeline
            logger.warning("FastVLM observe failed: %s", exc)
            return SceneObservation.failure(f"fastvlm error: {exc}", source=self.name)


def _result_text(out: object) -> str:
    """Normalize generate() output (str in old mlx-vlm, result object in new)."""
    if isinstance(out, str):
        return out
    for attr in ("text", "generation", "output"):
        val = getattr(out, attr, None)
        if isinstance(val, str):
            return val
    return str(out)
