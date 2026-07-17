import logging

from dotenv import load_dotenv

# WAJIB dipanggil PALING ATAS, sebelum import routes/services manapun —
# beberapa module (misal routes/sessions.py) baca environment variable
# langsung pas di-import, jadi .env harus udah ke-load duluan.
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import database
from routes import ingest, sessions, stats
from services.websocket_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="Judol Blocker Backend", version="0.1.0")

# CORS dibuka lebar untuk development. Persempit origin-nya nanti kalau sudah
# ada domain/host tetap untuk frontend-dashboard dan frontend-overlay.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(sessions.router)
app.include_router(stats.router)


@app.on_event("startup")
def on_startup():
    database.init_db()
    logger.info("Database siap.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Overlay dan dashboard sama-sama connect ke sini untuk nerima event
    'comment_processed' secara real-time.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Kita gak butuh nerima pesan dari client, cuma jaga koneksi tetap hidup.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
