import logging

from fastapi import APIRouter, HTTPException

import database
from models import IngestRequest, IngestResponse
from services.decision_logic import decide_status
from services.model_client import ModelServiceError, get_combined_judol_score
from services.websocket_manager import manager

logger = logging.getLogger("route-ingest")
router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_comment(payload: IngestRequest):
    # Validasi session ada dulu, biar gak nyimpen comment nyasar ke session yang gak exist
    session = database.get_session(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{payload.session_id}' tidak ditemukan")
    
    # 1. Minta skor dari model-service — cek 'message' DAN 'donator' (username),
    # ambil skor paling tinggi di antara keduanya. Ini nangkep kasus username
    # yang isinya promosi judol (mis. 'SlotGacor77'), bukan cuma isi pesannya.
    try:
        result = get_combined_judol_score(message=payload.message, donator=payload.donator)
        judol_score = result["score"]
        flagged_field = result["flagged_field"]
        logger.info(f"judol_score={judol_score:.4f} (dari field: {flagged_field})")
    except ModelServiceError as e:
        # 503 karena ini masalah service lain yang gak available, bukan salah request-nya
        raise HTTPException(status_code=503, detail=str(e))

    # 2. Decision logic
    status = decide_status(judol_score)

    # 3. Simpan ke DB
    comment = database.insert_comment(
        session_id=payload.session_id,
        donator=payload.donator,
        message=payload.message,
        amount=payload.amount,
        score=judol_score,
        status=status,
    )

    # 4. Broadcast ke overlay + dashboard.
    # Overlay & dashboard sama-sama nerima event ini, tapi overlay HARUS filter
    # sendiri di sisi frontend: cuma render kalau status == 'aman' atau 'diblokir'.
    # Kalau status == 'diblokir', overlay juga HARUS sembunyikan field 'message'
    # asli saat render (jangan tampilkan verbatim ke penonton), cukup tampilkan
    # status + score. Field 'message' tetap dikirim di payload websocket ini
    # karena dashboard (yang butuh auth) perlu lihat teks aslinya untuk review.
    await manager.broadcast("comment_processed", comment)

    return comment
