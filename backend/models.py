from typing import Optional

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    overlay_url: str = Field(..., description="URL widget overlay Saweria asli, mis. https://saweria.co/widgets/alert?streamKey=XXXX")
    owner_name: Optional[str] = None


class SessionCreateResponse(BaseModel):
    session_id: str
    overlay_url: str  # URL overlay pengganti (frontend-overlay kita), ditempel ke OBS


class IngestRequest(BaseModel):
    session_id: str
    donator: Optional[str] = None
    message: str = Field(..., min_length=1)
    amount: Optional[int] = None


class IngestResponse(BaseModel):
    id: str
    session_id: str
    donator: Optional[str]
    message: str
    amount: Optional[int]
    score: float
    status: str
    top_word: Optional[str] = None
    created_at: str


class SummaryResponse(BaseModel):
    total: int
    terdeteksi_judi: int
    diblokir: int
    aman: int


class TimeseriesPoint(BaseModel):
    bucket: str  # ISO timestamp awal bucket
    total: int
    diblokir: int
    aman: int


class TimeseriesResponse(BaseModel):
    points: list[TimeseriesPoint]
