"""Pydantic request/response schemas for the Video Intelligence API."""

from typing import Optional
from pydantic import BaseModel


class AnalyzeResponse(BaseModel):
    video_id: str
    status: str          # "queued"
    eta_seconds: Optional[int] = None


class StatusResponse(BaseModel):
    video_id: str
    status: str          # "queued" | "processing" | "complete" | "failed" | "not_found"
    progress_percent: int = 0
    current_stage: Optional[str] = None
    error: Optional[str] = None
