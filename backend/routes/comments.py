from typing import Optional

from fastapi import APIRouter

import database
from models import CommentsResponse

router = APIRouter()


@router.get("/comments", response_model=CommentsResponse)
def list_comments(
    session_id: str,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    """
    Histori komentar (terbaru duluan) — dipakai dashboard buat ngisi tabel
    real-time pas halaman pertama kali dibuka/di-refresh, sebelum ada event
    WebSocket baru yang lewat.
    """
    comments = database.get_comments(session_id, status=status, page=page, page_size=page_size)
    return {"comments": comments}
