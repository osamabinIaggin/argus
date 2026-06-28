"""
Tier 2 — gated semantic understanding ("what is happening").

A swappable vision-language backend (SceneUnderstander) run off the critical path
by Tier2Controller, gated by Tier-1 triggers + a heartbeat floor. Results flow
back into the Tier-3 scene state via tracker.note_semantic().

    from streaming.tier2 import Tier2Controller, FastVLMUnderstander
"""

from streaming.tier2.controller import Tier2Controller
from streaming.tier2.fastvlm_mlx import FastVLMUnderstander
from streaming.tier2.stub import StubSceneUnderstander
from streaming.tier2.understanding import SceneObservation, SceneUnderstander

__all__ = [
    "Tier2Controller",
    "SceneUnderstander",
    "SceneObservation",
    "StubSceneUnderstander",
    "FastVLMUnderstander",
]
