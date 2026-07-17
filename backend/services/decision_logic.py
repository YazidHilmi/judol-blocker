"""
Decision logic — mapping judol_score dari model ke status akhir.
Sistem 2 status: aman / diblokir. Threshold di-set lewat environment
variable biar gampang di-tune tanpa ubah kode.
"""

import os

THRESHOLD_BLOCK = float(os.environ.get("THRESHOLD_BLOCK", 0.50))


def decide_status(judol_score: float) -> str:
    """
    judol_score >= THRESHOLD_BLOCK  -> 'diblokir'
    judol_score <  THRESHOLD_BLOCK  -> 'aman'
    """
    return "diblokir" if judol_score >= THRESHOLD_BLOCK else "aman"
