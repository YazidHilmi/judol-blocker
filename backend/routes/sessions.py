import logging
import os
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, Depends, Header, HTTPException

import database
from models import SessionCreateRequest, SessionCreateResponse
from services.crypto_utils import decrypt_value, encrypt_value

logger = logging.getLogger("route-sessions")
router = APIRouter()

# URL frontend-overlay kita sendiri — di-generate lengkap dengan ?session=<id>
# lalu inilah yang ditempel streamer ke OBS, menggantikan URL Saweria asli.
OVERLAY_BASE_URL = os.environ.get("OVERLAY_BASE_URL", "http://localhost:3001/index.html")

# API key internal buat proteksi endpoint /internal/sessions/active.
# Adapter (Node.js) harus kirim key yang SAMA PERSIS lewat header
# 'X-Internal-Api-Key' di tiap request ke endpoint itu.
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY")

if not INTERNAL_API_KEY:
    INTERNAL_API_KEY = "dev-only-change-me"
    logger.warning(
        "INTERNAL_API_KEY tidak di-set di .env — pakai default dev yang TIDAK AMAN "
        "('dev-only-change-me'). Ini oke untuk development lokal, tapi WAJIB diganti "
        "ke value acak yang rahasia sebelum sistem ini diakses dari luar localhost. "
        "Generate value acak dengan: python -c \"import secrets; print(secrets.token_hex(32))\" "
        "lalu set INTERNAL_API_KEY di .env backend DAN di .env adapter dengan value yang sama."
    )


def verify_internal_api_key(x_internal_api_key: str = Header(None)):
    """
    Dependency buat proteksi endpoint internal. Cuma request yang bawa
    header X-Internal-Api-Key dengan value yang cocok yang boleh lewat.
    """
    if not x_internal_api_key or x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized — X-Internal-Api-Key tidak valid")


def extract_stream_key(overlay_url: str) -> str:
    """
    Ekstrak streamKey dari URL widget overlay Saweria.
    Format yang diharapkan: https://saweria.co/widgets/alert?streamKey=XXXX
    """
    try:
        parsed = urlparse(overlay_url)
    except Exception:
        raise ValueError("URL tidak valid")

    if not parsed.scheme or not parsed.netloc:
        raise ValueError("URL tidak valid — pastikan formatnya lengkap (https://...)")

    if "saweria.co" not in parsed.netloc:
        raise ValueError("URL bukan URL Saweria yang valid (domain harus saweria.co)")

    query_params = parse_qs(parsed.query)
    stream_key_values = query_params.get("streamKey")

    if not stream_key_values or not stream_key_values[0].strip():
        raise ValueError("streamKey tidak ditemukan di URL — pastikan lu copy URL widget overlay yang lengkap dari Saweria")

    return stream_key_values[0].strip()


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session(payload: SessionCreateRequest):
    try:
        stream_key = extract_stream_key(payload.overlay_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    encrypted_stream_key = encrypt_value(stream_key)

    session_id = database.create_session(
        stream_key=encrypted_stream_key,
        owner_name=payload.owner_name,
        platform="saweria",
    )

    logger.info(f"Session baru dibuat: {session_id} (owner: {payload.owner_name or 'tidak diisi'})")

    overlay_url = f"{OVERLAY_BASE_URL}?session={session_id}"

    return SessionCreateResponse(session_id=session_id, overlay_url=overlay_url)


@router.get("/internal/sessions/active")
def list_active_sessions(_: None = Depends(verify_internal_api_key)):
    """
    KHUSUS dipanggil oleh adapter/ (Node.js) — bukan buat diakses frontend/publik.
    Balikin semua session yang ada beserta streamKey yang SUDAH di-decrypt,
    supaya adapter bisa otomatis connect ke semua streamer yang terdaftar
    tanpa perlu streamKey di-input manual satu-satu di .env adapter.

    Dilindungi header X-Internal-Api-Key (lihat verify_internal_api_key di atas).
    Request tanpa header ini atau dengan value yang salah akan ditolak (401).
    """
    sessions = database.get_all_sessions()
    result = []
    for session in sessions:
        try:
            stream_key = decrypt_value(session["stream_key"])
        except Exception as e:
            logger.error(f"Gagal decrypt stream_key untuk session {session['id']}: {e}")
            continue
        result.append({
            "session_id": session["id"],
            "stream_key": stream_key,
            "owner_name": session["owner_name"],
            "platform": session["platform"],
        })
    return {"sessions": result}
