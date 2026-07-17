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


TOP_WORD_DROP_THRESHOLD = 0.20  # kata dianggap "berpengaruh" kalau nurunin skor >= 20%
TOP_WORD_MAX_COUNT = 3


def explain_top_word(text: str, baseline_score: float) -> list[str] | None:
    """
    Explainability sederhana pakai metode occlusion: buang 1 kata dari 'text',
    minta model nilai ulang sisa kalimatnya. Kata yang bikin skor turun paling
    banyak pas dibuang = kata yang paling "bertanggung jawab" atas skor tinggi.

    Cuma masuk akal dipanggil untuk komentar yang statusnya 'diblokir' — dipanggil
    dari routes/ingest.py, bukan dari sini, biar fungsi ini tetap murni.

    Balikin list kata (maks TOP_WORD_MAX_COUNT, cuma yang penurunan skornya
    >= TOP_WORD_DROP_THRESHOLD), diurutkan dari paling berpengaruh. None kalau
    gak ada kata yang cukup signifikan atau gagal (dianggap non-fatal, biar
    /ingest tetap sukses walau explainability-nya gagal).
    """
    words = text.split()
    if len(words) <= 1:
        return words or None

    # Bikin varian kalimat per kata yang dibuang, kirim SEKALIGUS dalam 1 batch
    # request (bukan N request terpisah) biar murah.
    variants = [" ".join(words[:i] + words[i + 1:]) for i in range(len(words))]

    try:
        response = httpx.post(
            f"{MODEL_SERVICE_URL}/predict",
            json={"texts": variants},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        predictions = response.json().get("predictions")
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning(f"Gagal explain_top_word (non-fatal, di-skip): {e}")
        return None

    if not predictions or len(predictions) != len(words):
        return None

    drops = [
        (word, baseline_score - prediction["judol_score"])
        for word, prediction in zip(words, predictions)
    ]
    drops.sort(key=lambda pair: pair[1], reverse=True)

    significant = [word for word, drop in drops if drop >= TOP_WORD_DROP_THRESHOLD]
    return significant[:TOP_WORD_MAX_COUNT] if significant else None
