/**
 * Script testing — kirim donasi PALSU ke session Saweria yang lagi aktif,
 * buat mastiin adapter beneran nangkep event dan forward ke backend, tanpa
 * perlu ada transaksi donasi asli.
 *
 * Jalankan ini di terminal TERPISAH, sementara index.js (npm start) lagi jalan.
 *
 * Cara pakai: node test-fake-donation.js
 * (otomatis pakai session pertama yang aktif; kalau mau pilih session
 * tertentu, jalankan: node test-fake-donation.js <session_id>)
 */

require("dotenv").config();
const axios = require("axios");
const { Client } = require("saweria");

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY;

if (!INTERNAL_API_KEY) {
  console.error("INTERNAL_API_KEY belum di-set di .env — harus sama dengan value di backend.");
  process.exit(1);
}

async function main() {
  const response = await axios.get(`${BACKEND_URL}/internal/sessions/active`, {
    headers: { "X-Internal-Api-Key": INTERNAL_API_KEY },
  });
  const sessions = response.data.sessions || [];

  if (sessions.length === 0) {
    console.error("Belum ada session aktif. Daftarin session dulu lewat POST /sessions atau form web.");
    process.exit(1);
  }

  const targetSessionId = process.argv[2];
  const session = targetSessionId
    ? sessions.find((s) => s.session_id === targetSessionId)
    : sessions[0];

  if (!session) {
    console.error(`Session dengan id '${targetSessionId}' tidak ditemukan di antara session aktif.`);
    process.exit(1);
  }

  console.log(`Mengirim donasi palsu ke session: ${session.session_id} (${session.owner_name || "tanpa nama"})`);

  const client = new Client();
  await client.setStreamKey(session.stream_key);

  // Catatan: sendFakeDonation() di saweria v2 butuh login (email+password Saweria)
  // dulu via client.login(), bukan cukup streamKey — endpoint fake donation-nya
  // baca header authorization (JWT), bukan stream-key. Kalau mau pakai script ini,
  // isi SAWERIA_EMAIL/SAWERIA_PASSWORD di .env lalu uncomment login() di bawah.
  // Untuk tes donasi asli, lebih gampang pakai fitur "kirim donasi tes" langsung
  // dari dashboard Saweria (gak perlu simpan password di mana pun).
  //
  // await client.login(process.env.SAWERIA_EMAIL, process.env.SAWERIA_PASSWORD);
  await client.sendFakeDonation();

  console.log("Donasi palsu terkirim. Cek terminal index.js, harusnya muncul log donasi masuk.");
  process.exit(0);
}

main().catch((err) => {
  console.error("Gagal kirim donasi palsu:", err.message || err);
  process.exit(1);
});
