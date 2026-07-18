# Judol Blocker — Project Spec & Status (Dataathon)

Dokumen kondisi terkini project. Paste ke chat/agent baru biar langsung paham konteks penuh tanpa baca ulang history. Untuk cara install & jalanin project, lihat [README.md](README.md).

**Terakhir diupdate:** 2026-07-17

---

## Konteks project

Sistem yang mendeteksi & memblokir komentar/pesan donasi bermuatan promosi judi online ("judol") secara real-time di platform donasi streamer **Saweria**, sebelum pesan tampil/dibacakan di layar live streaming (OBS).

- Kompetisi: dataathon (tim: Tyler + Aldi + partner ML)
- Role Tyler: **backend** (model dikerjakan partner)
- Model final: **IndoBERT** base, 2 label (`Normal`=0, `Judol`=1), fine-tuned partner via CRISP-DM pipeline

## Status keseluruhan: SISTEM LENGKAP, TERBUKTI JALAN END-TO-END DENGAN DONASI SAWERIA ASLI ✅

Integrasi Saweria asli + OBS udah diverifikasi jalan pakai donasi & replay alert beneran (bukan simulasi doang). Semua fitur inti + fitur tambahan (explainability, history, idempotent registration, redesign visual) udah selesai. Sisanya tinggal persiapan demo.

## Git

Project ini **udah jadi git repo** (`git init` 2026-07-17). History commit (urut lama→baru):

1. `150584f` — Checkpoint: sistem inti jalan end-to-end (Saweria asli → adapter → backend → overlay/dashboard)
2. `61d6fba` — Fitur explainability "kata pemicu" (occlusion)
3. `bab5b70` — Fix jam ketuker 7 jam (timezone bug)
4. `8c9c3d5` — Endpoint `GET /comments` (history biar tabel gak kosong pas refresh)
5. `c75aa2c` — `POST /sessions` idempotent (streamKey sama = balikin session lama)
6. `557769d` — Redesign visual dashboard & overlay → tema terang + drop shadow
7. `4f80485` — Redesign kartu alert overlay: rounded penuh, strip diganti bar+icon
8. `5cb2da0` — Format teks alert aman jadi kalimat "X baru saja memberikan RpY"

Kalau ada perubahan berikutnya bikin sistem rusak: `git diff` buat liat apa yang berubah, `git checkout <commit-hash> -- .` buat balik ke checkpoint manapun di atas.

`.gitignore` exclude: `.env` (secret), `venv/`, `node_modules/`, `judol_blocker.db`, dan **file model (`*.safetensors`, 475MB)** — model gak pernah diedit jadi gak perlu di-track, dan kegedean buat git normal (GitHub limit 100MB/file). Kalau clone repo ini di laptop lain, taro manual file model dari partner ke `model-service/model/`.

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

**Kenapa HTML/JS polos, bukan React:** keputusan sadar demi kecepatan development. Backend gak peduli FE pakai stack apa — kontraknya cuma REST + WebSocket. Sempat ditawarin ganti ke React pas visual mau di-redesign, tapi diputuskan tetap vanilla — redesign visual itu murni soal CSS, gak butuh framework, dan ganti framework di tengah jalan berisiko ngerusak sistem yang udah kebukti jalan.

**WebSocket, BUKAN webhook** (poin yang sempat bikin bingung): adapter kita yang **connect keluar** ke server Saweria (`wss://events.saweria.co/stream?streamKey=...`) dan "nguping" terus-menerus di situ. Ini kebalikan dari webhook (di mana Saweria yang nembak masuk ke server kita). Konsekuensinya: server kita gak perlu bisa diakses dari internet publik, gak butuh ngrok/domain/tunnel buat testing lokal.

## Alur bisnis end-to-end

1. Streamer buka `frontend-dashboard/register.html`, paste URL widget overlay Saweria asli (`https://saweria.co/widgets/alert?streamKey=XXXX`)
2. `POST /sessions` extract `streamKey`, **enkripsi** (Fernet), simpan ke DB. **Idempotent**: kalau streamKey ini udah pernah didaftarin, balikin `session_id` yang LAMA (bukan bikin baru) — jadi kalau streamer lupa link dashboard, tinggal daftar ulang pakai streamKey Saweria yang sama buat "recover". Balikin URL overlay pengganti + URL dashboard (otomatis nempel `?session=<id>`). Halaman hasil punya tombol **"Buka Dashboard →"** (buka tab baru) + tombol Salin
3. Streamer tempel URL overlay pengganti ke OBS (menggantikan URL Saweria default)
4. `adapter/` (Node.js) **polling** ke `GET /internal/sessions/active` tiap 10 detik (dilindungi API key), otomatis connect ke SEMUA session terdaftar — streamer baru daftar → adapter otomatis dengar donasinya **tanpa restart**
5. Adapter connect manual pakai `ws` ke `wss://events.saweria.co/stream?streamKey=...` (BUKAN pakai class `Client` dari package npm `saweria` — ada bug, lihat bagian bug). Nangkep event tipe `"donations"` (donasi baru) DAN `"donation"` (replay alert). Dedup donasi yang sama dalam window 8 detik.
6. Forward tiap donasi ke `POST /ingest`. Backend cek `message` DAN `donator` ke model-service terpisah, ambil skor **tertinggi** (nangkep username judol kayak `SlotGacor77`)
7. **Decision logic (2 status, TIDAK ADA review manual):**
   - `judol_score >= 0.50` → `diblokir`
   - `judol_score < 0.50` → `aman`
8. Kalau `diblokir`: jalankan **explainability (occlusion)** — cari kata yang paling berpengaruh ke skor, simpan sebagai `top_word` (maks 3 kata, threshold drop skor 20%)
9. Simpan ke DB, broadcast via WebSocket event `comment_processed` ke overlay + dashboard
10. **Overlay** (OBS): kartu putih rounded dengan drop shadow. Alert **aman**: teks "`{donator}` baru saja memberikan `Rp{amount}`" + pesan asli tampil, icon centang hijau. Alert **diblokir**: pesan asli **disembunyikan** (cuma skor yang tampil), icon silang merah — sengaja, biar konten judol gak ke-broadcast ke penonton
11. **Dashboard**: 4 kartu angka + grafik tren real-time + tabel real-time (dengan kolom "Kata Pemicu"), filter per `session_id` di URL. Tabel load history lama lewat `GET /comments` pas dibuka, gak kosong pas di-refresh.

## Kenapa "per user 1 dashboard" tanpa login

Keputusan sadar: pakai **capability URL** (kayak Google Docs share-link), bukan akun+password. `session_id` = UUID gak ketebak. Cukup aman untuk scope dataathon, jauh hemat waktu. Trade-off: link bocor = orang lain bisa lihat (read-only) — TAPI streamKey asli, akun Saweria, dan data finansial TIDAK PERNAH ke-expose lewat URL manapun (streamKey selalu terenkripsi di DB, cuma di-decrypt server-side buat adapter). Sudah dipertimbangkan menambah sistem auth penuh — diputuskan **tidak worth** untuk dataathon (effort ~1,5-2 hari, nilai kecil buat kompetisi, dan masalah "lupa session" udah kesolve lewat idempotent registration yang numpang ke auth Saweria yang udah ada).

---

## Status detail per komponen (semua SELESAI)

### Backend (`backend/`)
- `database.py` — skema SQLite: `sessions` (id, stream_key terenkripsi, platform, owner_name, created_at) + `comments_log` (id, session_id, donator, message, amount, score, status, **top_word**, created_at, dengan migrasi ALTER TABLE otomatis). Fungsi: `get_summary_stats()`, `get_timeseries_stats()` (bucket per menit buat grafik), `get_comments()` (history), `find_session_by_stream_key()` (buat idempotent registration)
- `services/decision_logic.py` — 2 status
- `services/model_client.py` — `get_combined_judol_score()` (cek message + donator), `explain_top_word()` (occlusion, threshold 20%, maks 3 kata)
- `services/crypto_utils.py` — enkripsi/dekripsi streamKey (Fernet)
- `services/websocket_manager.py` — broadcast `comment_processed`
- `routes/ingest.py` — endpoint inti (model → decision → occlusion kalau diblokir → DB → websocket)
- `routes/sessions.py` — `POST /sessions` (idempotent) + `GET /internal/sessions/active` (dilindungi API key)
- `routes/stats.py` — `GET /stats/summary` + `GET /stats/timeseries`
- `routes/comments.py` — `GET /comments` (history komentar, buat isi tabel dashboard pas refresh)
- `simulator.py` — kirim data dummy ke `/ingest` buat testing tanpa Saweria

### Frontend dashboard (`frontend/frontend-dashboard/`)
- `index.html` + `dashboard.js` + `style.css` — **tema terang** (background krem/putih, kartu drop-shadow), 4 kartu angka + grafik tren real-time (canvas vanilla, warna baca dari CSS var otomatis ngikut tema) + tabel real-time (load history dari `/comments` pas buka + kolom "Kata Pemicu")
- `register.html` + `register.js` — form daftar streamer, tema terang, tombol "Buka Dashboard"
- `config.js` — config terpusat port/URL

### Frontend overlay (`frontend/frontend-overlay/`)
- `index.html` + `overlay.js` + `style.css` — background TETAP transparan (wajib buat OBS), kartu alert **putih rounded penuh dengan drop shadow**, bar aksen warna tipis di tepi atas + icon badge bulat (centang/silang) sebagai pengganti garis strip. Alert aman formatnya kalimat "`{donator}` baru saja memberikan `Rp{amount}`"
- `config.js` — config terpusat

### Adapter (`adapter/`)
- `index.js` — Node.js, multi-session (polling based), forward donasi ke `/ingest`. **PENTING:** TIDAK pakai class `Client` dari package npm `saweria` — connect manual pakai `ws` langsung ke `wss://events.saweria.co/stream?streamKey=...`, karena library `saweria` v2.0.1 ada bug (lihat bagian bug)
- `test-fake-donation.js` — kirim donasi palsu via `sendFakeDonation()` (masih pakai package `saweria`, cuma buat trigger, bukan listen — dan butuh login email/password Saweria buat jalan di v2, jadi lebih praktis pakai fitur "Replay Alert" di dashboard Saweria buat testing gratis)
- `package.json`, `.env`
- Dedup donasi: donation id yang sama dalam window **8 detik** cuma diproses sekali

### Model service (`model-service/`)
- `model_service.py` — FastAPI, endpoint `/predict` + `/health`, preprocessing identik dengan training (`clean_text` → `normalize_emoji` → `normalize_unicode`)
- `model/` — 4 file HuggingFace (`config.json`, `model.safetensors`, `tokenizer.json`, `tokenizer_config.json`)

---

## REST API endpoints (aktual)

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/sessions` | Extract & simpan streamKey terenkripsi (idempotent), balikin session_id + URL overlay pengganti |
| POST | `/ingest` | Terima komentar, panggil model, decision logic, occlusion (kalau diblokir), simpan DB, broadcast WS |
| GET | `/stats/summary?session_id=` | `{total, terdeteksi_judi, diblokir, aman}` |
| GET | `/stats/timeseries?session_id=&interval_minutes=1` | Data per bucket waktu buat grafik tren |
| GET | `/comments?session_id=&status=&page=&page_size=` | History komentar (terbaru duluan), buat isi tabel dashboard |
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

**Peringatan penting:** kalau service dijalankan di terminal integrated VSCode, **nutup VSCode bakal ikut matiin semua service itu**. Buat sesi kerja panjang, lebih aman jalanin di PowerShell/terminal biasa yang independen dari VSCode.

## Cara testing cepat (tanpa Saweria/OBS asli)

1. Jalankan model-service + backend (2 terminal)
2. `cd backend && python simulator.py` — bikin session dummy, kirim 8 komentar campur, print hasil live
3. Buka `frontend-dashboard/index.html?session=<id>` — angka, grafik & tabel update real-time
4. Buka `frontend-overlay/index.html?session=<id>` — alert muncul

## Cara testing gratis pakai data Saweria asli (gak perlu bayar/donasi beneran)

Di dashboard Saweria (dashboard.saweria.co), halaman **Daftar Transaksi**, tiap transaksi lama ada tombol **"Replay Alert"** — ini ngirim ulang event donasi yang sama lewat WebSocket yang sama persis kayak donasi asli, **gratis**, gak perlu transfer lagi. Ini cara paling murah buat re-test adapter/backend/overlay tanpa keluar duit terus-terusan.

---

## Bug yang sudah difix (sesi 2026-07-16 & 2026-07-17)

**Sesi 2026-07-16:**
1. `simulator.py` crash di Windows console kalau komentar ada emoji → force stdout UTF-8
2. **KRITIS:** `frontend-overlay/index.html` gak load `config.js` → overlay gak pernah connect WebSocket. Fixed: tambah `<script src="config.js">`
3. `adapter/index.js` + `test-fake-donation.js` upgrade package `saweria` v1.3.2 → v2.0.1 (server lama `stream.saweria.co` udah mati, pindah ke `events.saweria.co`)

**Sesi 2026-07-17 (paling kritis — donasi Saweria asli gak pernah kedetect):**
4. **KRITIS PALING BESAR:** package npm `saweria@2.0.1` ada bug internal — dia cek `data.type === "donation"` (singular), padahal Saweria beneran ngirim `data.type === "donations"` (plural) buat donasi baru, dan `"donation"` (singular) khusus buat event **replay alert**. Gara-gara library cuma ngecek 1 dari 2 kemungkinan, donasi asli diam-diam diabaikan tanpa error. Ketauan lewat raw WebSocket debug listener manual. Fix: `adapter/index.js` connect manual (skip class `Client`), nangkep **DUA-DUANYA**.
5. `frontend-overlay/config.js` + `frontend-dashboard/config.js` port ke-ubah ke `8002` (harusnya `8000`), sumbernya gak ketauan. Fixed balikin ke `8000`.
6. Banyak proses `node.exe` zombie numpuk dari berkali-kali restart testing. Solusi: `taskkill /F /IM node.exe` sebelum restart adapter.
7. Duplikat registrasi session dengan streamKey asli yang sama (3-6x) bikin backend overload. Dibersihin manual, lalu dicegah permanen lewat idempotent registration (lihat bug/fitur berikutnya).
8. Tabel "Komentar real-time" di dashboard kosong tiap di-refresh (cuma nampung WebSocket event baru, gak fetch history). Fixed: endpoint `GET /comments` baru + `loadInitialFeed()`.
9. Jam di tabel & grafik dashboard ketuker 7 jam dari WIB asli — backend simpan `datetime.utcnow()` tanpa suffix `Z`, browser nganggep itu jam lokal apa adanya. Fixed di `formatTime()`/`bucketLabel()` (dashboard.js), tambah `Z` sebelum di-parse jadi `Date`.
10. `POST /sessions` selalu bikin session baru walau streamKey sama persis → numpuk session duplikat. Fixed: `find_session_by_stream_key()`, bikin endpoint idempotent.

**Cara debug yang kepake buat nemuin bug #4** (berguna kalau ada masalah serupa lagi): bikin script Node.js kecil pakai package `ws` langsung, connect ke `wss://events.saweria.co/stream?streamKey=<key>`, log SEMUA raw message yang masuk apa adanya (tanpa lewat library `saweria`). Ini nunjukin persis format asli yang dikirim Saweria, gak ketebak dari baca kode doang.

## Isu model (BUKAN bug, keterbatasan akurasi)

Model bener untuk kalimat dengan kata kunci eksplisit ("slot gacor maxwin jp" → 0.998, benar Judol), tapi **lemah untuk promosi generik tanpa kata kunci** ("daftar sekarang bonus new member 100%" → salah Normal). Ini keterbatasan data training partner, ranah retraining model, di luar scope backend.

## File model dari partner

Format standar HuggingFace `save_pretrained()`. `training_args.bin` tidak dipakai, boleh diabaikan. Preprocessing WAJIB identik dengan training (sudah diimplementasi di `model_service.py`). Model HANYA dari file lokal, tidak upload ke HuggingFace Hub.

---

## Yang belum kelar / perlu diperiksa

1. **🟡 Latensi klasifikasi belum diukur dengan valid** — sempat kelihatan lambat (~2.7 detik per komentar) pas dites, tapi pengukuran itu kejadian pas server lagi crash (VSCode ketutup), jadi datanya gak reliable. Perlu diukur ulang bersih. Kalau beneran lambat, coba dulu opsi murah (cek CPU vs GPU, kurangin `MAX_LENGTH`, batesin jumlah kata yang dicek occlusion) SEBELUM mikir ganti model — ganti model itu keputusan besar yang nyentuh wilayah partner (perlu retraining ulang, gak bisa asal ganti ke model lain yang belum pernah dilatih buat tugas ini).
2. **🟢 Persiapan demo:** skenario komentar, jawaban pertanyaan juri, slide/narasi

## Keputusan desain final (jangan diulang tanya)

- **2 status saja** (aman/diblokir), TIDAK ADA review manual
- **Tanpa login**, capability URL (session_id di query param) + idempotent registration sebagai mekanisme "recovery"
- **HTML/JS polos** untuk FE (bukan React) — termasuk pas redesign visual, tetap vanilla CSS
- **SQLite** untuk dev, bisa upgrade PostgreSQL (query kompatibel)
- **Grafik tren real-time per menit** (bukan tren harian) — pakai canvas vanilla, zero dependency biar aman demo offline
- **Explainability pakai occlusion**, bukan SHAP/Integrated Gradients — jauh lebih murah komputasi buat model-service 1-worker CPU
- **Model service dari file lokal**, tidak upload ke HuggingFace Hub
- **Semua bisa jalan 100% lokal** untuk demo — integrasi Saweria pakai WebSocket outbound (bukan webhook inbound), gak butuh domain publik

## Preferensi komunikasi Tyler

- Bahasa Indonesia casual (gw/lu), to the point, gak suka bertele-tele
- Suka feedback jujur/blak-blakan termasuk soal kualitas visual/desain
- Sering perlu diingetin balik ke blocker yang belum selesai (suka skip pertanyaan debugging lalu lanjut topik lain)
- Menghargai dikasih tau jelas file mana yang perlu ditimpa/dipindah setelah ada perubahan
- Suka nanya "bisa gak pake X" (framework, arsitektur alternatif) sebelum eksekusi — jawab jujur dengan trade-off, jangan langsung nolak atau langsung iyain
