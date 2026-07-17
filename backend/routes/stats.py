from fastapi import APIRouter

import database
from models import SummaryResponse, TimeseriesResponse

router = APIRouter()


@router.get("/stats/summary", response_model=SummaryResponse)
def stats_summary(session_id: str):
    return database.get_summary_stats(session_id)


@router.get("/stats/timeseries", response_model=TimeseriesResponse)
def stats_timeseries(session_id: str, interval_minutes: int = 1):
    points = database.get_timeseries_stats(session_id, interval_minutes)
    return {"points": points}
