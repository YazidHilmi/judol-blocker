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

function renderSafeAlert(comment) {
  const card = document.createElement("div");
  card.className = "alert-card alert-card--safe";
  card.innerHTML = `
    <div class="alert-top">
      <span class="alert-donator">${escapeHtml(comment.donator || "Anonim")}</span>
      <span class="alert-amount">${formatAmount(comment.amount)}</span>
    </div>
    <p class="alert-message">${escapeHtml(comment.message)}</p>
  `;
  return card;
}

function renderBlockedAlert(comment) {
  const scorePercent = (comment.score * 100).toFixed(0);
  const card = document.createElement("div");
  card.className = "alert-card alert-card--blocked";
  card.innerHTML = `
    <div class="alert-top">
      <span class="alert-donator">Komentar diblokir</span>
    </div>
    <p class="alert-blocked-label">Terindikasi promosi judi online</p>
    <p class="alert-score">Skor deteksi: ${scorePercent}%</p>
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
