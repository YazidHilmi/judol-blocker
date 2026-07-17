"""
WebSocket manager — simple connection pool + broadcast.
Overlay dan dashboard connect ke endpoint yang sama (/ws), filtering
status yang mau ditampilkan dikerjakan di sisi frontend masing-masing
(lihat catatan di routes/ingest.py).
"""

import json
import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger("websocket-manager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total koneksi: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total koneksi: {len(self.active_connections)}")

    async def broadcast(self, event: str, payload: dict):
        """Kirim event ke semua client yang lagi connect (overlay + dashboard sekaligus)."""
        message = json.dumps({"event": event, "data": payload})
        dead_connections = set()

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Gagal kirim ke satu client, akan di-remove: {e}")
                dead_connections.add(connection)

        for dead in dead_connections:
            self.active_connections.discard(dead)


manager = ConnectionManager()
