"""
Simulator — nembak komentar dummy ke /ingest, buat testing tanpa perlu
Saweria/adapter beneran.

Cara pakai:
1. Pastikan backend (main.py) dan model-service udah jalan
2. Jalankan: python simulator.py
   (otomatis bikin session dev dulu kalau belum ada SESSION_ID di env)
"""

import os
import random
import sys
import time

import httpx

# Console Windows default (cp1252) gak bisa render emoji di pesan dummy judol
# (🔥, 😍) — paksa stdout ke utf-8 biar gak crash pas print.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

DUMMY_NORMAL = [
    ("BudiSantoso", "semangat terus bang, sehat selalu ya"),
    ("MegaWin77", "streamnya keren banget hari ini"),
    ("RajaMaxwin_88", "makasih infonya bermanfaat banget"),
    ("AkunBaru123", "lanjut terus contentnya kak"),
]

DUMMY_JUDOL = [
    ("SlotGacor77", "slot gacor hari ini bosku, maxwin auto jp 🔥"),
    ("bit.ly/slotgacor", "daftar sekarang bonus new member 100% 😍"),
    ("MegaWin77", "info slot paling gacor hari ini ada disini bit.ly/jpmaxwin"),
    ("AkunBaru123", "ikut group depo 10k WD 1jt langsung gas!"),
]


def get_or_create_session() -> str:
    session_id = os.environ.get("SESSION_ID")
    if session_id:
        return session_id

    # Pakai endpoint /sessions asli — URL Saweria dummy tapi formatnya valid
    # (domain saweria.co + query param streamKey), biar ekstraksi streamKey-nya
    # ikut ke-test juga, bukan cuma bikin session kosong.
    resp = httpx.post(
        f"{BACKEND_URL}/sessions",
        json={
            "overlay_url": "https://saweria.co/widgets/alert?streamKey=dummy-test-key-123",
            "owner_name": "test-streamer",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    session_id = data["session_id"]
    print(f"Session dibuat: {session_id}")
    print(f"URL overlay pengganti: {data['overlay_url']}")
    print(f"(set env SESSION_ID={session_id} kalau mau pakai session yang sama lagi)\n")
    return session_id


def send_comment(session_id: str, donator: str, message: str):
    payload = {
        "session_id": session_id,
        "donator": donator,
        "message": message,
        "amount": random.choice([5000, 10000, 20000, 50000]),
    }
    resp = httpx.post(f"{BACKEND_URL}/ingest", json=payload, timeout=15.0)
    resp.raise_for_status()
    result = resp.json()
    print(f"[{result['status'].upper():10}] score={result['score']:.3f} | {donator}: {message}")


def main():
    session_id = get_or_create_session()
    all_comments = DUMMY_NORMAL + DUMMY_JUDOL
    random.shuffle(all_comments)

    for donator, message in all_comments:
        try:
            send_comment(session_id, donator, message)
        except httpx.HTTPStatusError as e:
            print(f"Error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            print(f"Gagal connect ke backend: {e}")
        time.sleep(1.5)


if __name__ == "__main__":
    main()
