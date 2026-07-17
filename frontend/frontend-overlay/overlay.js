const BACKEND_WS = window.CONFIG.BACKEND_WS;
const ALERT_DURATION_MS = 6000; // berapa lama 1 alert tampil sebelum hilang

const params = new URLSearchParams(window.location.search);
const sessionId = params.get("session");

const stack = document.getElementById("alert-stack");

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatAmount(amount) {
  if (!amount) return "";
  return `Rp${Number(amount).toLocaleString("id-ID")}`;
}

// Icon badge bulat di tiap kartu — pengganti garis strip warna di kiri,
// biar kartunya bisa rounded penuh 4 sisi tapi tetap ada aksen visual.
const ICON_CHECK = `<svg viewBox="0 0 24 24" width="22" height="22"><path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2.75" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICON_BLOCKED = `<svg viewBox="0 0 24 24" width="22" height="22"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.75" fill="none" stroke-linecap="round"/></svg>`;

function renderSafeAlert(comment) {
  const card = document.createElement("div");
  card.className = "alert-card alert-card--safe";
  card.innerHTML = `
    <div class="alert-icon">${ICON_CHECK}</div>
    <div class="alert-body">
      <p class="alert-top">
        <span class="alert-donator">${escapeHtml(comment.donator || "Anonim")}</span>
        baru saja memberikan
        <span class="alert-amount">${formatAmount(comment.amount)}</span>
      </p>
      <p class="alert-message">${escapeHtml(comment.message)}</p>
    </div>
  `;
  return card;
}

function renderBlockedAlert(comment) {
  const scorePercent = (comment.score * 100).toFixed(0);
  const card = document.createElement("div");
  card.className = "alert-card alert-card--blocked";
  card.innerHTML = `
    <div class="alert-icon">${ICON_BLOCKED}</div>
    <div class="alert-body">
      <div class="alert-top">
        <span class="alert-donator">Komentar diblokir</span>
      </div>
      <p class="alert-blocked-label">Terindikasi promosi judi online</p>
      <p class="alert-score">Skor deteksi: ${scorePercent}%</p>
    </div>
  `;
  return card;
}

function showAlert(comment) {
  // Overlay HANYA render status 'aman' dan 'diblokir' — sistem sekarang
  // cuma 2 status, gak ada antrian review manual.
  let card;
  if (comment.status === "aman") {
    card = renderSafeAlert(comment);
  } else if (comment.status === "diblokir") {
    card = renderBlockedAlert(comment);
  } else {
    return;
  }

  stack.appendChild(card);

  setTimeout(() => {
    card.classList.add("leaving");
    setTimeout(() => card.remove(), 300);
  }, ALERT_DURATION_MS);
}

function connectWebSocket() {
  const ws = new WebSocket(BACKEND_WS);

  ws.onclose = () => setTimeout(connectWebSocket, 2000);

  ws.onmessage = (event) => {
    let parsed;
    try {
      parsed = JSON.parse(event.data);
    } catch {
      return;
    }

    if (parsed.event !== "comment_processed") return;
    const comment = parsed.data;

    if (sessionId && comment.session_id !== sessionId) return;

    showAlert(comment);
  };
}

connectWebSocket();
