"""
Client buat manggil model-service (FastAPI terpisah yang jalan di :8001).
"""

import os
import logging

import httpx

logger = logging.getLogger("model-client")

MODEL_SERVICE_URL = os.environ.get("MODEL_SERVICE_URL", "http://localhost:8001")
REQUEST_TIMEOUT = float(os.environ.get("MODEL_SERVICE_TIMEOUT", 10.0))


class ModelServiceError(Exception):
    """Dilempar kalau model-service gak bisa dihubungi atau balikin error."""
    pass


def get_judol_score(text: str) -> float:
    """
    Kirim 1 teks ke model-service, balikin judol_score (0.0-1.0).
    Raise ModelServiceError kalau gagal, biar caller (route /ingest) bisa
    handle dengan response error yang jelas ke client, bukan crash.
    """
    try:
        response = httpx.post(
            f"{MODEL_SERVICE_URL}/predict",
            json={"texts": [text]},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.RequestError as e:
        logger.error(f"Gagal connect ke model-service: {e}")
        raise ModelServiceError(f"Model service tidak bisa dihubungi: {e}") from e
    except httpx.HTTPStatusError as e:
        logger.error(f"Model-service balikin error status: {e}")
        raise ModelServiceError(f"Model service error: {e.response.status_code}") from e

    data = response.json()
    predictions = data.get("predictions")
    if not predictions:
        raise ModelServiceError("Response model-service tidak berisi predictions")

    return predictions[0]["judol_score"]


def get_combined_judol_score(message: str, donator: str | None = None) -> dict:
    """
    Cek judol_score untuk 'message' dan 'donator' (username) secara terpisah,
    lalu ambil yang paling tinggi sebagai skor final.

    Catatan: model ini dilatih pakai komentar (kalimat), bukan username, jadi
    hasil untuk 'donator' sifatnya heuristik tambahan — tetap berguna untuk
    menangkap kasus username yang jelas-jelas promosi (mis. 'SlotGacor77',
    'bit.ly/slotgacor'), tapi jangan diperlakukan seakurat skor dari 'message'.

    Balikin dict: {"score": float, "flagged_field": "message" | "donator" | None}
    """
    texts_to_check = [("message", message)]
    if donator and donator.strip():
        texts_to_check.append(("donator", donator))

    try:
        response = httpx.post(
            f"{MODEL_SERVICE_URL}/predict",
            json={"texts": [t for _, t in texts_to_check]},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.RequestError as e:
        logger.error(f"Gagal connect ke model-service: {e}")
        raise ModelServiceError(f"Model service tidak bisa dihubungi: {e}") from e
    except httpx.HTTPStatusError as e:
        logger.error(f"Model-service balikin error status: {e}")
        raise ModelServiceError(f"Model service error: {e.response.status_code}") from e

    predictions = response.json().get("predictions")
    if not predictions:
        raise ModelServiceError("Response model-service tidak berisi predictions")

    best_score = -1.0
    best_field = None
    for (field_name, _), prediction in zip(texts_to_check, predictions):
        score = prediction["judol_score"]
        if score > best_score:
            best_score = score
            best_field = field_name

    return {"score": best_score, "flagged_field": best_field}
