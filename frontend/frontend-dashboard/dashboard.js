const BACKEND_HTTP = window.CONFIG.BACKEND_HTTP;
const BACKEND_WS = window.CONFIG.BACKEND_WS;

const params = new URLSearchParams(window.location.search);
const sessionId = params.get("session");

const el = {
  sessionLabel: document.getElementById("session-id-label"),
  liveDot: document.getElementById("live-dot"),
  liveText: document.getElementById("live-text"),
  statTotal: document.getElementById("stat-total"),
  statTerdeteksi: document.getElementById("stat-terdeteksi"),
  statDiblokir: document.getElementById("stat-diblokir"),
  statAman: document.getElementById("stat-aman"),
  feedBody: document.getElementById("feed-body"),
  chartCanvas: document.getElementById("trend-chart"),
};

const chartCtx = el.chartCanvas.getContext("2d");
const chartColors = {
  grid: getComputedStyle(document.documentElement).getPropertyValue("--border").trim() || "#262c35",
  muted: getComputedStyle(document.documentElement).getPropertyValue("--text-muted").trim() || "#8b93a1",
  total: getComputedStyle(document.documentElement).getPropertyValue("--accent-pulse").trim() || "#22d3c7",
  diblokir: getComputedStyle(document.documentElement).getPropertyValue("--accent-danger").trim() || "#f0475a",
};

const CHART_INTERVAL_MINUTES = 1;
const CHART_MAX_BUCKETS = 20;
const chartBuckets = new Map(); // bucketKey (ISO menit) -> { bucket, total, diblokir, aman }

const STATUS_LABEL = {
  aman: "Aman",
  diblokir: "Diblokir",
};

function setLiveStatus(state, text) {
  el.liveDot.className = `live-dot ${state}`;
  el.liveText.textContent = text;
}

function flashStat(node, newValue) {
  node.textContent = newValue;
  node.classList.remove("flash");
  // force reflow biar animasi bisa re-trigger tiap update
  void node.offsetWidth;
  node.classList.add("flash");
}

function formatTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function truncate(text, maxLength = 80) {
  if (!text) return "";
  return text.length > maxLength ? text.slice(0, maxLength) + "…" : text;
}

async function loadInitialSummary() {
  if (!sessionId) return;
  try {
    const res = await fetch(`${BACKEND_HTTP}/stats/summary?session_id=${encodeURIComponent(sessionId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    el.statTotal.textContent = data.total;
    el.statTerdeteksi.textContent = data.terdeteksi_judi;
    el.statDiblokir.textContent = data.diblokir;
    el.statAman.textContent = data.aman;
  } catch (err) {
    console.error("Gagal load summary awal:", err);
  }
}

function addFeedRow(comment) {
  // Hapus baris "belum ada komentar" kalau masih ada
  const emptyRow = el.feedBody.querySelector(".feed-empty-row");
  if (emptyRow) emptyRow.remove();

  const row = document.createElement("tr");
  row.className = "feed-row-new";

  const statusClass = `status-badge status-badge--${comment.status}`;
  const statusLabel = STATUS_LABEL[comment.status] || comment.status;

  row.innerHTML = `
    <td class="col-time">${formatTime(comment.created_at)}</td>
    <td>${escapeHtml(comment.donator || "-")}</td>
    <td class="col-message">${escapeHtml(truncate(comment.message))}</td>
    <td class="col-score">${(comment.score * 100).toFixed(1)}%</td>
    <td><span class="${statusClass}">${statusLabel}</span></td>
  `;

  el.feedBody.prepend(row);

  // Batasi maksimal 50 baris biar gak berat kalau dashboard dibiarkan lama
  const rows = el.feedBody.querySelectorAll("tr:not(.feed-empty-row)");
  if (rows.length > 50) {
    rows[rows.length - 1].remove();
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function updateStatsFromComment(status) {
  const total = parseInt(el.statTotal.textContent, 10) + 1;
  flashStat(el.statTotal, total);

  if (status === "diblokir") {
    const terdeteksi = parseInt(el.statTerdeteksi.textContent, 10) + 1;
    flashStat(el.statTerdeteksi, terdeteksi);
    const diblokir = parseInt(el.statDiblokir.textContent, 10) + 1;
    flashStat(el.statDiblokir, diblokir);
  } else if (status === "aman") {
    const aman = parseInt(el.statAman.textContent, 10) + 1;
    flashStat(el.statAman, aman);
  }
}

// Backend simpan created_at sebagai string ISO naive (tanpa timezone) — dibaca
// apa adanya sebagai teks biar bucket key di sini selalu sinkron persis sama
// bucket yang dihitung backend di get_timeseries_stats(), tanpa drift timezone.
function bucketKeyFromIso(isoString, intervalMinutes) {
  const datePart = isoString.slice(0, 10);
  const hour = isoString.slice(11, 13);
  const minute = parseInt(isoString.slice(14, 16), 10);
  const bucketMinute = Math.floor(minute / intervalMinutes) * intervalMinutes;
  return `${datePart}T${hour}:${String(bucketMinute).padStart(2, "0")}:00`;
}

function bucketLabel(bucketKey) {
  return new Date(bucketKey).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}

async function loadInitialTimeseries() {
  if (!sessionId) return;
  try {
    const res = await fetch(
      `${BACKEND_HTTP}/stats/timeseries?session_id=${encodeURIComponent(sessionId)}&interval_minutes=${CHART_INTERVAL_MINUTES}`
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    chartBuckets.clear();
    for (const point of data.points) {
      chartBuckets.set(point.bucket, point);
    }
    renderChart();
  } catch (err) {
    console.error("Gagal load tren awal:", err);
  }
}

function recordCommentInChart(comment) {
  const key = bucketKeyFromIso(comment.created_at, CHART_INTERVAL_MINUTES);
  if (!chartBuckets.has(key)) {
    chartBuckets.set(key, { bucket: key, total: 0, diblokir: 0, aman: 0 });
  }
  const point = chartBuckets.get(key);
  point.total += 1;
  if (comment.status === "diblokir") point.diblokir += 1;
  else if (comment.status === "aman") point.aman += 1;
  renderChart();
}

function renderChart() {
  const dpr = window.devicePixelRatio || 1;
  const width = el.chartCanvas.parentElement.clientWidth - 40; // dikurangi padding kiri+kanan section
  const height = 220;

  el.chartCanvas.width = width * dpr;
  el.chartCanvas.height = height * dpr;
  el.chartCanvas.style.width = `${width}px`;
  el.chartCanvas.style.height = `${height}px`;
  chartCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  chartCtx.clearRect(0, 0, width, height);

  const buckets = [...chartBuckets.values()]
    .sort((a, b) => a.bucket.localeCompare(b.bucket))
    .slice(-CHART_MAX_BUCKETS);

  const padding = { top: 12, right: 8, bottom: 24, left: 30 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  if (buckets.length === 0) {
    chartCtx.fillStyle = chartColors.muted;
    chartCtx.font = "13px 'Space Grotesk', sans-serif";
    chartCtx.textAlign = "center";
    chartCtx.textBaseline = "middle";
    chartCtx.fillText("Belum ada data buat digrafikkan.", width / 2, height / 2);
    return;
  }

  const maxValue = Math.max(1, ...buckets.map((b) => b.total));
  const stepX = buckets.length > 1 ? plotWidth / (buckets.length - 1) : 0;

  const xAt = (i) => padding.left + (buckets.length === 1 ? plotWidth / 2 : i * stepX);
  const yAt = (value) => padding.top + plotHeight - (value / maxValue) * plotHeight;

  chartCtx.strokeStyle = chartColors.grid;
  chartCtx.lineWidth = 1;
  chartCtx.font = "10.5px 'JetBrains Mono', monospace";
  chartCtx.fillStyle = chartColors.muted;
  chartCtx.textAlign = "right";
  chartCtx.textBaseline = "middle";

  const gridLines = 4;
  for (let g = 0; g <= gridLines; g++) {
    const value = Math.round((maxValue / gridLines) * g);
    const y = yAt(value);
    chartCtx.beginPath();
    chartCtx.moveTo(padding.left, y);
    chartCtx.lineTo(width - padding.right, y);
    chartCtx.stroke();
    chartCtx.fillText(String(value), padding.left - 8, y);
  }

  chartCtx.textAlign = "center";
  chartCtx.textBaseline = "top";
  const labelEvery = Math.max(1, Math.ceil(buckets.length / 6));
  buckets.forEach((b, i) => {
    if (i % labelEvery === 0 || i === buckets.length - 1) {
      chartCtx.fillText(bucketLabel(b.bucket), xAt(i), height - padding.bottom + 8);
    }
  });

  function drawLine(valueKey, color) {
    chartCtx.beginPath();
    buckets.forEach((b, i) => {
      const x = xAt(i);
      const y = yAt(b[valueKey]);
      if (i === 0) chartCtx.moveTo(x, y);
      else chartCtx.lineTo(x, y);
    });
    chartCtx.strokeStyle = color;
    chartCtx.lineWidth = 2;
    chartCtx.lineJoin = "round";
    chartCtx.stroke();

    buckets.forEach((b, i) => {
      chartCtx.beginPath();
      chartCtx.arc(xAt(i), yAt(b[valueKey]), 3, 0, Math.PI * 2);
      chartCtx.fillStyle = color;
      chartCtx.fill();
    });
  }

  drawLine("total", chartColors.total);
  drawLine("diblokir", chartColors.diblokir);
}

window.addEventListener("resize", () => renderChart());

function connectWebSocket() {
  const ws = new WebSocket(BACKEND_WS);

  ws.onopen = () => setLiveStatus("connected", "Terhubung");
  ws.onclose = () => {
    setLiveStatus("error", "Terputus, mencoba lagi…");
    setTimeout(connectWebSocket, 2000);
  };
  ws.onerror = () => setLiveStatus("error", "Error koneksi");

  ws.onmessage = (event) => {
    let parsed;
    try {
      parsed = JSON.parse(event.data);
    } catch {
      return;
    }

    if (parsed.event !== "comment_processed") return;
    const comment = parsed.data;

    // Filter: dashboard ini cuma nampilin komentar dari session yang lagi dibuka
    if (sessionId && comment.session_id !== sessionId) return;

    addFeedRow(comment);
    updateStatsFromComment(comment.status);
    recordCommentInChart(comment);
  };
}

function init() {
  if (!sessionId) {
    el.sessionLabel.textContent = "tidak ada session_id di URL";
    setLiveStatus("error", "Tambahkan ?session=<id> di URL");
    return;
  }

  el.sessionLabel.textContent = sessionId;
  loadInitialSummary();
  loadInitialTimeseries();
  connectWebSocket();
}

init();
