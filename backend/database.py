"""
Database setup — pakai SQLite untuk development/demo (MVP).
Kalau nanti butuh production beneran, tinggal ganti connection string
ke PostgreSQL, query di bawah ini kompatibel untuk keduanya.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "judol_blocker.db"


def init_db():
    """Bikin tabel kalau belum ada. Panggil ini sekali pas startup aplikasi."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            TEXT PRIMARY KEY,
                stream_key    TEXT NOT NULL,
                platform      TEXT DEFAULT 'saweria',
                owner_name    TEXT,
                created_at    TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comments_log (
                id            TEXT PRIMARY KEY,
                session_id    TEXT NOT NULL,
                donator       TEXT,
                message       TEXT NOT NULL,
                amount        INTEGER,
                score         REAL,
                status        TEXT NOT NULL,
                top_word      TEXT,
                reviewed_by   TEXT,
                reviewed_at   TEXT,
                created_at    TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        # Kolom top_word ditambahin belakangan — kalau DB lama udah ada dari
        # sebelum fitur ini, CREATE TABLE IF NOT EXISTS di atas gak nambahin
        # kolom baru ke tabel yang udah ada. Tambahin manual kalau belum ada.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(comments_log)")}
        if "top_word" not in existing_columns:
            conn.execute("ALTER TABLE comments_log ADD COLUMN top_word TEXT")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_session
            ON comments_log(session_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_status
            ON comments_log(session_id, status)
        """)
        conn.commit()


@contextmanager
def get_connection():
    """Context manager biar koneksi selalu ke-close, dan row bisa diakses kayak dict."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(stream_key: str, owner_name: Optional[str] = None, platform: str = "saweria") -> str:
    """Simpan session baru, balikin session_id-nya."""
    session_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (id, stream_key, platform, owner_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, stream_key, platform, owner_name, datetime.utcnow().isoformat()),
        )
        conn.commit()
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def get_all_sessions() -> list[dict]:
    """Dipakai adapter buat tau semua session yang aktif dan perlu di-listen."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def insert_comment(
    session_id: str,
    donator: Optional[str],
    message: str,
    amount: Optional[int],
    score: float,
    status: str,
    top_word: Optional[list[str]] = None,
) -> dict:
    """Simpan 1 komentar yang udah diproses (ada score & status-nya), balikin data lengkapnya."""
    comment_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()
    top_word_str = ", ".join(top_word) if top_word else None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO comments_log
                (id, session_id, donator, message, amount, score, status, top_word, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (comment_id, session_id, donator, message, amount, score, status, top_word_str, created_at),
        )
        conn.commit()

    return {
        "id": comment_id,
        "session_id": session_id,
        "donator": donator,
        "message": message,
        "amount": amount,
        "score": score,
        "status": status,
        "top_word": top_word_str,
        "created_at": created_at,
    }


def get_comments(
    session_id: str,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> list[dict]:
    offset = (page - 1) * page_size
    query = "SELECT * FROM comments_log WHERE session_id = ?"
    params: list = [session_id]

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, offset])

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_summary_stats(session_id: str) -> dict:
    """Hitung total, terdeteksi_judi (sama dengan diblokir, sistem 2 status), diblokir, aman."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'diblokir' THEN 1 ELSE 0 END) AS diblokir,
                SUM(CASE WHEN status = 'aman' THEN 1 ELSE 0 END) AS aman
            FROM comments_log
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

    diblokir = row["diblokir"] or 0
    return {
        "total": row["total"] or 0,
        "terdeteksi_judi": diblokir,  # sistem 2 status: setiap yang terdeteksi otomatis diblokir
        "diblokir": diblokir,
        "aman": row["aman"] or 0,
    }


def get_timeseries_stats(session_id: str, interval_minutes: int = 1) -> list[dict]:
    """
    Hitung jumlah komentar per bucket waktu (default per menit), buat grafik tren.
    created_at disimpan sebagai ISO string UTC tanpa timezone suffix, jadi bucket-nya
    dihitung dengan membulatkan ke kelipatan interval_minutes lewat strftime.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                created_at,
                status
            FROM comments_log
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        dt = datetime.fromisoformat(row["created_at"])
        bucket_minute = (dt.minute // interval_minutes) * interval_minutes
        bucket_dt = dt.replace(minute=bucket_minute, second=0, microsecond=0)
        bucket_key = bucket_dt.isoformat()

        if bucket_key not in buckets:
            buckets[bucket_key] = {"bucket": bucket_key, "total": 0, "diblokir": 0, "aman": 0}

        buckets[bucket_key]["total"] += 1
        if row["status"] == "diblokir":
            buckets[bucket_key]["diblokir"] += 1
        elif row["status"] == "aman":
            buckets[bucket_key]["aman"] += 1

    return [buckets[key] for key in sorted(buckets.keys())]
