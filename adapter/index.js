/**
 * Adapter — jembatan antara Saweria dan backend judol-blocker.
 *
 * BEDA dari versi sebelumnya: adapter ini sekarang BISA MENANGANI BANYAK
 * STREAMER SEKALIGUS, bukan cuma 1 yang di-hardcode di .env. Caranya:
 * 1. Adapter polling ke backend tiap beberapa detik, nanya "session mana
 *    aja yang aktif sekarang beserta streamKey-nya" (streamKey didapat
 *    dari database backend, sudah otomatis di-decrypt oleh backend).
 * 2. Untuk tiap session baru yang belum di-connect, adapter bikin koneksi
 *    baru ke Saweria pakai streamKey session itu.
 * 3. Setiap donasi yang masuk dari koneksi manapun, di-forward ke /ingest
 *    dengan session_id yang sesuai.
 *
 * Jadi begitu ada streamer baru submit URL Saweria mereka lewat web
 * (POST /sessions), adapter ini OTOMATIS mulai dengerin donasi mereka
 * dalam beberapa detik, TANPA perlu restart adapter atau edit .env manual.
 *
 * Cara pakai:
 * 1. npm install
 * 2. Copy .env.example jadi .env (biasanya default-nya udah cukup)
 * 3. npm start
 */

require("dotenv").config();
const axios = require("axios");
const WebSocket = require("ws");

// Catatan: TIDAK pakai class Client dari package "saweria" (v2.0.1) — library itu
// punya bug, dia cek `data.type === "donation"` (singular) padahal Saweria beneran
// ngirim `data.type === "donations"` (plural, ada 's'). Gara-gara typo itu, SEMUA
// donasi asli diam-diam diabaikan, gak ada error/log sama sekali. Sudah dikonfirmasi
// lewat raw WebSocket listener (lihat riwayat debugging). Makanya di sini kita connect
// manual pakai package "ws" langsung ke endpoint event Saweria, skip library-nya.
const SAWERIA_STREAM_URL = "wss://events.saweria.co/stream";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const BACKEND_INGEST_URL = process.env.BACKEND_INGEST_URL || `${BACKEND_URL}/ingest`;
const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL_MS || "10000", 10);
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY;

if (!INTERNAL_API_KEY) {
  console.error(
    "[adapter] INTERNAL_API_KEY belum di-set di .env. Value ini HARUS SAMA PERSIS " +
    "dengan INTERNAL_API_KEY di .env backend, kalau tidak endpoint /internal/sessions/active " +
    "akan menolak (401 Unauthorized). Cek .env.example untuk contoh."
  );
  process.exit(1);
}

// Simpan koneksi aktif: session_id -> WebSocket instance
const activeConnections = new Map();

// Saweria kadang ngirim donasi yang SAMA berkali-kali beruntun dalam hitungan
// milidetik (terutama pas replay alert, bisa sampai 11x dalam <2 detik) — dedup
// pakai id donasi biar gak diproses/ditampilkan dobel di overlay. Dibatasi per
// JENDELA WAKTU (bukan block permanen), biar tetep bisa dites ulang berkali-kali
// (misal klik "Replay Alert" lagi beberapa detik kemudian dianggap tes baru).
const DEDUP_WINDOW_MS = 8000;
const recentDonationIds = new Map(); // donationId -> timestamp terakhir diproses

function isDuplicateDonation(donationId) {
  if (!donationId) return false;
  const now = Date.now();
  const lastSeen = recentDonationIds.get(donationId);
  recentDonationIds.set(donationId, now);

  // Bersihin entry basi biar Map gak numpuk tanpa batas kalau adapter jalan lama
  for (const [id, ts] of recentDonationIds) {
    if (now - ts > DEDUP_WINDOW_MS) recentDonationIds.delete(id);
  }

  return lastSeen !== undefined && now - lastSeen < DEDUP_WINDOW_MS;
}

async function forwardToBackend(sessionId, donation) {
  const payload = {
    session_id: sessionId,
    donator: donation.donator || donation.name || "Anonim",
    message: donation.message || "",
    amount: donation.amount || 0,
  };

  try {
    const response = await axios.post(BACKEND_INGEST_URL, payload, { timeout: 15000 });
    const result = response.data;
    console.log(
      `[adapter][${sessionId.slice(0, 8)}] [${result.status.toUpperCase()}] ` +
      `score=${result.score.toFixed(3)} | ${payload.donator}: ${payload.message}`
    );
  } catch (err) {
    if (err.response) {
      console.error(`[adapter][${sessionId.slice(0, 8)}] Backend error ${err.response.status}: ${JSON.stringify(err.response.data)}`);
    } else {
      console.error(`[adapter][${sessionId.slice(0, 8)}] Gagal connect ke backend: ${err.message}`);
    }
  }
}

function connectSession(sessionId, streamKey, ownerName) {
  console.log(`[adapter] Menghubungkan session baru: ${sessionId.slice(0, 8)} (${ownerName || "tanpa nama"})`);

  // Daftarkan duluan ke map biar polling berikutnya (10 dtk lagi) gak nyoba
  // connect session yang sama dua kali. Kalau setup gagal, dihapus lagi di handler error.
  const ws = new WebSocket(`${SAWERIA_STREAM_URL}?streamKey=${streamKey}`);
  activeConnections.set(sessionId, ws);

  ws.on("open", () => {
    console.log(`[adapter][${sessionId.slice(0, 8)}] Listener Saweria aktif, menunggu donasi...`);
  });

  ws.on("message", (raw) => {
    let data;
    try {
      data = JSON.parse(raw.toString());
    } catch (err) {
      console.error(`[adapter][${sessionId.slice(0, 8)}] Gagal parse pesan dari Saweria: ${err.message}`);
      return;
    }

    // Saweria pakai DUA nama type buat kejadian yang sama-sama harus diproses:
    // "donations" (plural) buat donasi baru yang beneran masuk, dan "donation"
    // (singular) buat event replay (tombol "Replay Alert" di dashboard Saweria).
    // Keduanya sama-sama bawa field "data" berisi array donasi, jadi ditangani sama.
    if ((data.type === "donations" || data.type === "donation") && Array.isArray(data.data)) {
      for (const donation of data.data) {
        if (isDuplicateDonation(donation.id)) continue;
        forwardToBackend(sessionId, donation);
      }
    }
  });

  ws.on("error", (err) => {
    console.error(`[adapter][${sessionId.slice(0, 8)}] Error koneksi Saweria: ${err.message || err}`);
  });

  ws.on("close", () => {
    console.log(`[adapter][${sessionId.slice(0, 8)}] Koneksi Saweria putus, akan dicoba ulang di polling berikutnya.`);
    activeConnections.delete(sessionId);
  });
}

async function pollActiveSessions() {
  try {
    const response = await axios.get(`${BACKEND_URL}/internal/sessions/active`, {
      timeout: 10000,
      headers: { "X-Internal-Api-Key": INTERNAL_API_KEY },
    });
    const sessions = response.data.sessions || [];

    for (const session of sessions) {
      if (!activeConnections.has(session.session_id)) {
        connectSession(session.session_id, session.stream_key, session.owner_name);
      }
    }

    if (sessions.length === 0 && activeConnections.size === 0) {
      console.log("[adapter] Belum ada session aktif. Menunggu streamer daftar lewat web...");
    }
  } catch (err) {
    if (err.response && err.response.status === 401) {
      console.error(
        "[adapter] Gagal polling: 401 Unauthorized. INTERNAL_API_KEY di .env adapter " +
        "tidak cocok dengan INTERNAL_API_KEY di .env backend. Samakan dulu kedua value itu."
      );
    } else {
      console.error(`[adapter] Gagal polling session aktif ke backend: ${err.message}`);
    }
  }
}

async function main() {
  console.log(`[adapter] Mulai polling session aktif tiap ${POLL_INTERVAL_MS / 1000} detik...`);
  await pollActiveSessions();
  setInterval(pollActiveSessions, POLL_INTERVAL_MS);
}

main().catch((err) => {
  console.error("[adapter] Fatal error:", err);
  process.exit(1);
});
