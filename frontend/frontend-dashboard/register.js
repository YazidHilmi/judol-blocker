const BACKEND_HTTP = window.CONFIG.BACKEND_HTTP;
const DASHBOARD_BASE_URL = window.CONFIG.DASHBOARD_BASE_URL;

const form = document.getElementById("register-form");
const submitBtn = document.getElementById("submit-btn");
const errorEl = document.getElementById("form-error");
const resultCard = document.getElementById("result-card");
const resultOverlayUrl = document.getElementById("result-overlay-url");
const resultDashboardUrl = document.getElementById("result-dashboard-url");
const openDashboardBtn = document.getElementById("open-dashboard-btn");

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function hideError() {
  errorEl.hidden = true;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError();

  const overlayUrl = document.getElementById("overlay-url").value.trim();
  const ownerName = document.getElementById("owner-name").value.trim();

  submitBtn.disabled = true;
  submitBtn.textContent = "Mendaftarkan...";

  try {
    const res = await fetch(`${BACKEND_HTTP}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        overlay_url: overlayUrl,
        owner_name: ownerName || null,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      showError(data.detail || "Gagal mendaftarkan URL, coba cek formatnya lagi.");
      return;
    }

    const dashboardUrl = `${DASHBOARD_BASE_URL}?session=${data.session_id}`;
    resultOverlayUrl.value = data.overlay_url;
    resultDashboardUrl.value = dashboardUrl;
    openDashboardBtn.href = dashboardUrl;
    resultCard.hidden = false;
    form.reset();
  } catch (err) {
    showError("Gagal menghubungi server. Pastikan backend sedang berjalan.");
    console.error(err);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Daftarkan";
  }
});

document.querySelectorAll(".copy-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetInput = document.getElementById(btn.dataset.target);
    targetInput.select();
    navigator.clipboard.writeText(targetInput.value).then(() => {
      const original = btn.textContent;
      btn.textContent = "Tersalin!";
      setTimeout(() => (btn.textContent = original), 1500);
    });
  });
});
