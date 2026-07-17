# Judol Blocker — Project Spec & Status (Dataathon)

Dokumen kondisi terkini project. Paste ke chat/agent baru biar langsung paham konteks penuh tanpa baca ulang history.

**Terakhir diupdate:** 2026-07-16

---

## Konteks project

Sistem yang mendeteksi & memblokir komentar/pesan donasi bermuatan promosi judi online ("judol") secara real-time di platform donasi streamer **Saweria**, sebelum pesan tampil/dibacakan di layar live streaming (OBS).

- Kompetisi: dataathon (tim: Tyler + Aldi + partner ML)
- Role Tyler: **backend** (model dikerjakan partner)
- Model final: **IndoBERT** base, 2 label (`Normal`=0, `Judol`=1), fine-tuned partner via CRISP-DM pipeline

## Status keseluruhan: SEMUA TAHAP CODING SELESAI ✅

Yang tersisa bukan coding, tapi **verifikasi integrasi Saweria asli + OBS** (cuma bisa dites Tyler pakai akun Saweria sendiri) + persiapan demo.

---

## Arsitektur (5 komponen terpisah, connect via HTTP/WebSocket)

```
judol-blocker/
├── model-service/          → Python FastAPI, inference IndoBERT (port 8001)
├── backend/                → Python FastAPI, otak utama (port 8000)
├── adapter/                → Node.js, jembatan ke Saweria asli (polling, no port)
└── frontend/
    ├── frontend-dashboard/ → HTML/JS polos: statistik + grafik + form daftar (port 3002)
    └── frontend-overlay/   → HTML/JS polos: ditempel ke OBS Browser Source (port 3001)
```

**Prinsip desain:** tiap folder berdiri sendiri, punya venv/node_modules sendiri, jalan di port beda, komunikasi HANYA lewat REST API + WebSocket. Tidak ada dependency antar folder di level filesystem/import.

**Kenapa HTML/JS polos, bukan React:** keputusan sadar demi kecepatan development. Backend gak peduli FE pakai stack apa — kontraknya cuma REST + WebSocket, jadi bisa di-rewrite ke React kapan aja tanpa nyentuh backend.

## Alur bisnis end-to-end

1. Streamer buka `frontend-dashboard/register.html`, paste URL widget overlay Saweria asli (`https://saweria.co/widgets/alert?streamKey=XXXX`)
2. `POST /sessions` extract `streamKey`, **enkripsi** (Fernet), simpan ke DB dengan `session_id` baru, balikin URL overlay pengganti + URL dashboard (otomatis nempel `?session=<id>`). Halaman hasil punya tombol **"Buka Dashboard →"** (buka tab baru) + tombol Salin
3. Streamer tempel URL overlay pengganti ke OBS (menggantikan URL Saweria default)
4. `adapter/` (Node.js) **polling** ke `GET /internal/sessions/active` tiap 10 detik (dilindungi API key), otomatis connect ke SEMUA session terdaftar — streamer baru daftar → adapter otomatis dengar donasinya **tanpa restart**
5. Adapter pakai library `saweria` (npm) listen event `donations` real-time, forward tiap donasi ke `POST /ingest`
6. Backend cek `message` DAN `donator` ke model-service terpisah, ambil skor **tertinggi** (nangkep username judol kayak `SlotGacor77`)
7. **Decision logic (2 status, TIDAK ADA review manual):**
   - `judol_score >= 0.50` → `diblokir`
   - `judol_score < 0.50` → `aman`
8. Simpan ke DB, broadcast via WebSocket event `comment_processed` ke overlay + dashboard
9. **Overlay** (OBS): alert hijau kalau `aman` (pesan asli tampil), banner merah kalau `diblokir` (pesan asli **disembunyikan**, cuma tampil skor — sengaja, biar konten judol gak ke-broadcast ke penonton)
10. **Dashboard**: 4 kartu angka + grafik tren real-time + tabel real-time, filter per `session_id` di URL

## Kenapa "per user 1 dashboard" tanpa login

Keputusan sadar: pakai **capability URL** (kayak Google Docs share-link), bukan akun+password. `session_id` = UUID gak ketebak. Cukup aman untuk scope dataathon, jauh hemat waktu. Trade-off: link bocor = orang lain bisa lihat (read-only). Sudah dipertimbangkan menambah sistem auth penuh — diputuskan **tidak worth** untuk dataathon (effort ~1,5-2 hari, nilai kecil buat kompetisi).

---

## Status detail per komponen (semua SELESAI)

### Backend (`backend/`)
- `database.py` — skema SQLite: `sessions` (id, stream_key terenkripsi, platform, owner_name, created_at) + `comments_log` (id, session_id, donator, message, amount, score, status, created_at). Fungsi `get_summary_stats()` + `get_timeseries_stats()` (bucket per menit buat grafik)
- `services/decision_logic.py` — 2 status
- `services/model_client.py` — `get_combined_judol_score()` cek message + donator
- `services/crypto_utils.py` — enkripsi/dekripsi streamKey (Fernet)
- `services/websocket_manager.py` — broadcast `comment_processed`
- `routes/ingest.py` — endpoint inti (model → decision → DB → websocket)
- `routes/sessions.py` — `POST /sessions` + `GET /internal/sessions/active` (dilindungi API key)
- `routes/stats.py` — `GET /stats/summary` + `GET /stats/timeseries`
- `simulator.py` — kirim data dummy ke `/ingest` buat testing tanpa Saweria

### Frontend dashboard (`frontend/frontend-dashboard/`)
- `index.html` + `dashboard.js` + `style.css` — 4 kartu angka + **grafik tren real-time** (canvas vanilla, tanpa library eksternal) + tabel real-time
- `register.html` + `register.js` — form daftar streamer, sudah di-style penuh (card layout, tombol "Buka Dashboard")
- `config.js` — config terpusat port/URL (biar gak hardcoded di banyak file)

### Frontend overlay (`frontend/frontend-overlay/`)
- `index.html` + `overlay.js` + `style.css` — 2-state alert (aman/diblokir), background transparan buat OBS
- `config.js` — config terpusat

### Adapter (`adapter/`)
- `index.js` — Node.js, multi-session (polling based), forward donasi ke `/ingest`
- `test-fake-donation.js` — kirim donasi palsu via `sendFakeDonation()` buat testing
- `package.json`, `.env`

### Model service (`model-service/`)
- `model_service.py` — FastAPI, endpoint `/predict` + `/health`, preprocessing identik dengan training (`clean_text` → `normalize_emoji` → `normalize_unicode`)
- `model/` — 4 file HuggingFace (`config.json`, `model.safetensors`, `tokenizer.json`, `tokenizer_config.json`)

---

## REST API endpoints (aktual)

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/sessions` | Extract & simpan streamKey terenkripsi, balikin session_id + URL overlay pengganti |
| POST | `/ingest` | Terima komentar, panggil model, decision logic, simpan DB, broadcast WS |
| GET | `/stats/summary?session_id=` | `{total, terdeteksi_judi, diblokir, aman}` |
| GET | `/stats/timeseries?session_id=&interval_minutes=1` | Data per bucket waktu buat grafik tren |
| GET | `/internal/sessions/active` | (API key) daftar session aktif + streamKey ter-decrypt, dipakai adapter |
| WS | `/ws` | Broadcast event `comment_processed` ke overlay + dashboard |

## Environment variables (WAJIB di-set sebelum demo)

**`backend/.env`:**
```
THRESHOLD_BLOCK=0.50
MODEL_SERVICE_URL=http://localhost:8001
OVERLAY_BASE_URL=http://localhost:3001/index.html
ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
INTERNAL_API_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
```
**`adapter/.env`:** `INTERNAL_API_KEY` HARUS SAMA PERSIS dengan backend.

> Tanpa key di-set, sistem tetap jalan pakai fallback dev-mode + warning, TAPI data lama gak kebaca lagi kalau restart (ENCRYPTION_KEY). **Status: sudah keisi di kedua `.env`.**

## Port tiap service

| Service | Port | Command |
|---|---|---|
| model-service | 8001 | `uvicorn model_service:app --port 8001` |
| backend | 8000 | `uvicorn main:app --port 8000` |
| frontend-dashboard | 3002 | `python -m http.server 3002` |
| frontend-overlay | 3001 | `python -m http.server 3001` |
| adapter | — | `npm start` |

> Catatan: dashboard di **3002** (bukan 3000 — 3000 sempat kena block). Cek `config.js` kalau ganti port.

## Cara testing cepat (tanpa Saweria/OBS asli)

1. Jalankan model-service + backend (2 terminal)
2. `cd backend && python simulator.py` — bikin session dummy, kirim 8 komentar campur, print hasil live
3. Buka `frontend-dashboard/index.html?session=<id>` — angka, grafik & tabel update real-time
4. Buka `frontend-overlay/index.html?session=<id>` — alert muncul

---

## Bug yang sudah difix (sesi 2026-07-16)

1. `simulator.py` crash di Windows console kalau komentar ada emoji → force stdout UTF-8
2. **KRITIS:** `frontend-overlay/index.html` gak load `config.js` → overlay gak pernah connect WebSocket (bakal blank total di OBS). Fixed: tambah `<script src="config.js">`
3. **KRITIS:** `adapter/index.js` + `test-fake-donation.js` salah import `Client` dari package `saweria` (`const { Client }` → harusnya `const Client = require("saweria")`, karena package pakai `export =`). Tanpa fix ini adapter gak pernah bisa connect ke Saweria

## Isu model (BUKAN bug, keterbatasan akurasi)

Model bener untuk kalimat dengan kata kunci eksplisit ("slot gacor maxwin jp" → 0.998, benar Judol), tapi **lemah untuk promosi generik tanpa kata kunci** ("daftar sekarang bonus new member 100%" → salah Normal). Ini keterbatasan data training partner, ranah retraining model, di luar scope backend.

## File model dari partner

Format standar HuggingFace `save_pretrained()`. `training_args.bin` tidak dipakai, boleh diabaikan. Preprocessing WAJIB identik dengan training (sudah diimplementasi di `model_service.py`). Model HANYA dari file lokal, tidak upload ke HuggingFace Hub.

---

## Yang belum kelar / langkah berikutnya (urut prioritas)

1. **🔴 Tes Saweria asli + OBS (belum pernah dites, cuma Tyler yang bisa):**
   - Daftar pakai streamKey Saweria **asli** lewat `register.html`
   - Jalanin adapter (`npm start`) → cek muncul log `"Terhubung ke Saweria, menunggu donasi..."`
   - Tempel URL overlay pengganti ke OBS Browser Source
   - Kirim test donation dari Saweria → cek muncul di overlay & dashboard, cek komen judol beneran kehalau
   - **Ini risiko terbesar yang belum ketutup** — semua fitur lain sudah kebukti via simulasi
2. **🟢 Persiapan demo:** skenario komentar, jawaban pertanyaan juri, slide/narasi

## Keputusan desain final (jangan diulang tanya)

- **2 status saja** (aman/diblokir), TIDAK ADA review manual
- **Tanpa login**, capability URL (session_id di query param)
- **HTML/JS polos** untuk FE (bukan React)
- **SQLite** untuk dev, bisa upgrade PostgreSQL (query kompatibel)
- **Grafik tren real-time per menit** (bukan tren harian) — pakai canvas vanilla, zero dependency biar aman demo offline
- **Model service dari file lokal**, tidak upload ke HuggingFace Hub
- **Semua bisa jalan 100% lokal** untuk demo — integrasi Saweria pakai WebSocket outbound (bukan webhook inbound), gak butuh domain publik

## Preferensi komunikasi Tyler

- Bahasa Indonesia casual (gw/lu), to the point, gak suka bertele-tele
- Suka feedback jujur/blak-blakan termasuk soal kualitas visual/desain
- Sering perlu diingetin balik ke blocker yang belum selesai (suka skip pertanyaan debugging lalu lanjut topik lain)
- Menghargai dikasih tau jelas file mana yang perlu ditimpa/dipindah setelah ada perubahan
