# Judol Blocker

Sistem yang mendeteksi & memblokir komentar/pesan donasi bermuatan promosi judi online ("judol") secara real-time di platform donasi streamer **Saweria**, sebelum pesan tampil di layar live streaming (OBS).

Dokumen ini isinya cara **install & jalanin** project ini dari nol. Untuk konteks/status project (bug yang udah difix, keputusan desain, dll), lihat [PROJECT_SPEC.md](PROJECT_SPEC.md).

---

## Prasyarat

Pastikan sudah terinstal di komputer:

- **Python 3.12** (atau 3.10+) — [python.org](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **Git**
- File model dari partner: `config.json`, `model.safetensors`, `tokenizer.json`, `tokenizer_config.json` (~475MB, gak ikut ke-clone dari git karena kegedean — minta terpisah)
- (Opsional, buat demo penuh) **OBS Studio** — [obsproject.com](https://obsproject.com/)
- (Opsional) Akun **Saweria** aktif — buat integrasi donasi asli

---

## 1. Clone & taruh file model

```bash
git clone <url-repo-ini>
cd indobert
```

Taruh 4 file model dari partner ke folder `model-service/model/`:

```
model-service/model/
├── config.json
├── model.safetensors
├── tokenizer.json
└── tokenizer_config.json
```

`training_args.bin` (kalau ada) tidak dipakai, boleh diabaikan.

---

## 2. Setup tiap komponen

Project ini terdiri dari **5 komponen independen**, tiap komponen punya environment sendiri.

### model-service (Python)

```bash
cd model-service
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### backend (Python)

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Mac/Linux

pip install -r requirements.txt

# Setup environment variables
copy .env.example .env     # Windows
# cp .env.example .env     # Mac/Linux
```

Buka `backend/.env`, isi `ENCRYPTION_KEY` dan `INTERNAL_API_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste hasilnya masing-masing ke `ENCRYPTION_KEY=` dan `INTERNAL_API_KEY=` di `.env`.

### adapter (Node.js)

```bash
cd adapter
npm install

copy .env.example .env     # Windows
# cp .env.example .env     # Mac/Linux
```

Buka `adapter/.env`, isi `INTERNAL_API_KEY` dengan **value yang SAMA PERSIS** kayak yang di `backend/.env`.

### frontend-dashboard & frontend-overlay

Gak butuh install apa-apa — HTML/JS/CSS polos, cukup di-serve pakai `python -m http.server`.

---

## 3. Jalankan semua service

Butuh **5 terminal terpisah**, tiap terminal biarin tetap jalan (jangan ditutup).

> ⚠️ **Kalau pakai terminal integrated VSCode, nutup VSCode bakal ikut matiin semua service.** Buat sesi kerja yang panjang, lebih aman jalanin di PowerShell/terminal biasa yang independen.

**Terminal 1 — model-service (port 8001):**
```bash
cd model-service
venv\Scripts\activate
uvicorn model_service:app --port 8001
```
Tunggu sampai muncul log `Model berhasil di-load`.

**Terminal 2 — backend (port 8000):**
```bash
cd backend
venv\Scripts\activate
uvicorn main:app --port 8000
```

**Terminal 3 — frontend-dashboard (port 3002):**
```bash
cd frontend/frontend-dashboard
python -m http.server 3002
```

**Terminal 4 — frontend-overlay (port 3001):**
```bash
cd frontend/frontend-overlay
python -m http.server 3001
```

**Terminal 5 — adapter** (baru dinyalain SETELAH ada minimal 1 streamer terdaftar, lihat langkah 4):
```bash
cd adapter
npm start
```

Cek semua sehat:
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```
Dua-duanya harus balikin `{"status":"ok", ...}`.

---

## 4. Cara testing — 2 opsi

### Opsi A: Testing cepat tanpa Saweria/OBS asli (simulator)

Dengan model-service + backend udah jalan (Terminal 1 & 2):

```bash
cd backend
venv\Scripts\activate
python simulator.py
```

Script ini otomatis bikin session dummy, kirim 8 komentar campur (judol & normal), dan nge-print hasil klasifikasinya. Copy `session_id` yang di-print, lalu buka:

- Dashboard: `http://localhost:3002/index.html?session=<session_id>`
- Overlay: `http://localhost:3001/index.html?session=<session_id>`

Kartu angka, grafik, dan tabel di dashboard harus update. Alert harus muncul di overlay.

### Opsi B: Testing penuh dengan Saweria asli + OBS

1. Buka `http://localhost:3002/register.html`
2. Login ke akun Saweria kamu, buka menu **Widget/Overlay**, copy URL widget alert (`https://saweria.co/widgets/alert?streamKey=...`)
3. Paste ke form, submit — dapat URL overlay pengganti + tombol "Buka Dashboard"
4. Nyalain adapter (Terminal 5): `npm start` — tunggu sampai muncul log `Listener Saweria aktif, menunggu donasi...`
5. Di OBS: tambah **Source → Browser**, isi URL dengan URL overlay pengganti dari langkah 3, Width `1920`, Height `1080`
6. Kirim donasi tes lewat Saweria (nominal di atas ambang minimum alert Saweria kamu, biasanya Rp10.000), atau — **lebih murah, gratis** — klik tombol **"Replay Alert"** di halaman Daftar Transaksi Saweria buat re-trigger donasi lama tanpa bayar lagi
7. Cek 3 tempat: terminal adapter (harus muncul log donasi masuk), dashboard, dan preview OBS

---

## Troubleshooting

**Overlay/dashboard gak update walau backend sehat** — kemungkinan besar cache browser/OBS. Hard refresh (`Ctrl+Shift+R`) di browser, atau di OBS: klik source → Properties → "Refresh cache of current page".

**Adapter gagal connect / donasi gak kedeteksi** — pastikan `INTERNAL_API_KEY` di `backend/.env` dan `adapter/.env` **sama persis**. Cek juga gak ada proses Node.js zombie numpuk dari testing sebelumnya (`taskkill /F /IM node.exe` di Windows lalu restart adapter).

**Port sudah dipakai (`address already in use`)** — ada proses lain masih pegang port itu. Cek dengan `netstat -ano | findstr :8000` (Windows), matikan proses lama sebelum start yang baru.

**`ModuleNotFoundError` / `Cannot find module`** — pastikan venv/node_modules yang aktif itu punya komponen yang lagi dijalankan (tiap folder punya environment sendiri, jangan campur).

Untuk detail bug-bug yang pernah kejadian selama development dan cara fix-nya, lihat bagian "Bug yang sudah difix" di [PROJECT_SPEC.md](PROJECT_SPEC.md).
