"""
Model inference service — klasifikasi komentar judi online (judol).

Cara pakai:
1. Taruh file ini di satu folder yang sama dengan file model:
   config.json, model.safetensors, tokenizer.json, tokenizer_config.json
2. Install dependencies: pip install fastapi uvicorn torch transformers emoji unidecode
3. Jalankan: uvicorn model_service:app --host 0.0.0.0 --port 8001
   (jalankan dengan 1 worker saja untuk MVP, lihat catatan di bawah)
4. Cek /health untuk memastikan model ke-load dengan benar
5. Kirim POST ke /predict dengan body {"texts": ["komentar 1", "komentar 2"]}

Catatan: jangan jalankan dengan --workers > 1, karena tiap worker akan
me-load model terpisah ke memory (boros RAM/VRAM). Untuk MVP, 1 worker cukup.
"""

import html
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import List

import numpy as np
import torch
from emoji import demojize
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from torch.utils.data import Dataset, DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from unidecode import unidecode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("judol-classifier")

# Path model bisa di-override lewat environment variable, default ke folder file ini
MODEL_PATH = Path(os.environ.get("MODEL_PATH", Path(__file__).resolve().parent))
MAX_LENGTH = int(os.environ.get("MODEL_MAX_LENGTH", 128))
BATCH_SIZE = int(os.environ.get("MODEL_BATCH_SIZE", 8))

app = FastAPI(title="Judol Comment Classifier", version="1.0.0")


# ---------------------------------------------------------------------------
# Request / response schema
# ---------------------------------------------------------------------------

class PredictionRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, description="List teks komentar yang mau diklasifikasi")


class PredictionItem(BaseModel):
    text: str
    preprocessed_text: str
    label: str
    label_id: int
    confidence: float
    judol_score: float  # ini yang dipakai decision logic backend utama (threshold 0.9 / 0.5)
    probabilities: dict


class PredictionResponse(BaseModel):
    predictions: List[PredictionItem]
    model_path: str


# ---------------------------------------------------------------------------
# Preprocessing — HARUS identik dengan preprocessing saat training,
# supaya distribusi input saat inference sama dengan saat model dilatih.
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Hapus noise teknis: HTML entity/tag, URL, mention, timestamp, karakter berulang."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"@[\w.\-]+", "", text)
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", "", text)
    text = re.sub(r"([a-zA-Z])\1{2,}", r"\1\1", text)
    text = re.sub(r"([!?.]){3,}", r"\1\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_emoji(text: str) -> str:
    """Ubah emoji jadi representasi teks (demojize), misal 🔥 -> :fire:"""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    demojized = demojize(text, delimiters=(" :", ": "))
    return re.sub(r"\s+", " ", demojized).strip()


def normalize_unicode(text: str) -> str:
    """Normalisasi karakter unicode dekoratif/non-latin jadi bentuk latin standar."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.category(c).startswith("M")
    )
    return unidecode(text)


def preprocess_text(text: str) -> str:
    text = clean_text(text)
    text = normalize_emoji(text)
    text = normalize_unicode(text)
    return text.strip()


# ---------------------------------------------------------------------------
# Dataset untuk batch inference
# ---------------------------------------------------------------------------

class RawTextDataset(Dataset):
    def __init__(self, texts: List[str], tokenizer, max_length: int):
        self.texts = texts
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx: int):
        encoding = self.tokenizer(
            self.texts[idx],
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
            padding="max_length",
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
        }


# ---------------------------------------------------------------------------
# Model service
# ---------------------------------------------------------------------------

class ModelService:
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        required_files = ["config.json", "tokenizer_config.json"]
        missing = [f for f in required_files if not (model_path / f).exists()]
        if missing:
            raise RuntimeError(
                f"File model tidak lengkap di '{model_path}'. "
                f"File yang hilang: {missing}. "
                f"Pastikan config.json, model.safetensors, tokenizer.json, "
                f"dan tokenizer_config.json ada di folder yang sama dengan script ini."
            )

        try:
            logger.info(f"Loading tokenizer & model dari: {model_path}")
            self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(model_path))
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"Model berhasil di-load di device: {self.device}")
        except Exception as e:
            raise RuntimeError(f"Gagal load model dari '{model_path}': {e}") from e

    def predict_proba(self, texts: List[str], batch_size: int = BATCH_SIZE) -> np.ndarray:
        cleaned = [preprocess_text(text) for text in texts]
        dataset = RawTextDataset(cleaned, self.tokenizer, MAX_LENGTH)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)

        all_probs = []
        with torch.no_grad():
            for batch in loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
                probs = torch.softmax(outputs.logits, dim=-1)
                all_probs.append(probs.cpu().numpy())

        if not all_probs:
            return np.empty((0, 2), dtype=float)
        return np.vstack(all_probs)


try:
    service = ModelService(MODEL_PATH)
    MODEL_LOADED = True
    MODEL_LOAD_ERROR = None
except Exception as e:
    # Jangan crash saat import — biarkan /health melaporkan errornya dengan jelas,
    # supaya gampang di-debug ("kenapa service ini gak jalan?") daripada cuma
    # traceback mentah pas start up.
    service = None
    MODEL_LOADED = False
    MODEL_LOAD_ERROR = str(e)
    logger.error(f"Model gagal di-load: {e}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    if not MODEL_LOADED:
        return {"status": "error", "detail": MODEL_LOAD_ERROR}
    return {"status": "ok", "model_path": str(MODEL_PATH), "device": str(service.device)}


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    if not MODEL_LOADED:
        raise HTTPException(
            status_code=503,
            detail=f"Model belum ter-load: {MODEL_LOAD_ERROR}",
        )

    if not request.texts:
        raise HTTPException(status_code=400, detail="texts tidak boleh kosong")

    try:
        probs = service.predict_proba(request.texts)
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Gagal melakukan inference: {e}")

    if probs.shape[0] != len(request.texts):
        raise HTTPException(status_code=500, detail="Jumlah hasil prediksi tidak sesuai jumlah input")

    id2label = {0: "Normal", 1: "Judol"}

    results = []
    for idx, prob in enumerate(probs):
        label_id = int(np.argmax(prob))
        confidence = float(prob[label_id])
        label_name = id2label.get(label_id, str(label_id))

        results.append(PredictionItem(
            text=request.texts[idx],
            preprocessed_text=preprocess_text(request.texts[idx]),
            label=label_name,
            label_id=label_id,
            confidence=round(confidence, 6),
            judol_score=round(float(prob[1]), 6),
            probabilities={
                "Normal": round(float(prob[0]), 6),
                "Judol": round(float(prob[1]), 6),
            },
        ))

    return PredictionResponse(predictions=results, model_path=str(MODEL_PATH))
