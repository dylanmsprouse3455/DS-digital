const API_BASE = "https://kali.tail768496.ts.net";
const CONSENT_VERSION = "2026-05-24";
const CONSENT_CHOICE_KEY = "dsDigitalQrConsentStatus";
const CONSENT_ID_KEY = "dsDigitalQrConsentId";

const presets = {
  classic: {
    qr: "#111827",
    bg: "#ffffff",
    card: "#ffffff",
    text: "#111827",
    muted: "#475467",
    accent: "#2563eb",
    border: "#dbe3ef",
    shadow: "0 18px 44px rgba(17, 24, 39, 0.1)"
  },
  "ds-purple": {
    qr: "#5b21b6",
    bg: "#ffffff",
    card: "#fbf9ff",
    text: "#1f1933",
    muted: "#5d5378",
    accent: "#7c3aed",
    border: "#ddd6fe",
    shadow: "0 20px 50px rgba(124, 58, 237, 0.18)"
  },
  dark: {
    qr: "#ffffff",
    bg: "#111827",
    card: "#111827",
    text: "#ffffff",
    muted: "#d1d5db",
    accent: "#60a5fa",
    border: "#293548",
    shadow: "0 24px 60px rgba(0, 0, 0, 0.28)"
  },
  soft: {
    qr: "#6d28d9",
    bg: "#f6f2ff",
    card: "#faf7ff",
    text: "#241238",
    muted: "#6b5f7d",
    accent: "#a78bfa",
    border: "#e9d5ff",
    shadow: "0 18px 46px rgba(109, 40, 217, 0.13)"
  }
};

let selectedDesign = "classic";
let latestQr = null;

const form = document.getElementById("qrForm");
const statusEl = document.getElementById("formStatus");
const qrContainer = document.getElementById("qrcode");
const emptyState = document.getElementById("emptyState");
const downloadBtn = document.getElementById("downloadBtn");
const copyBtn = document.getElementById("copyBtn");
const titleInput = document.getElementById("cardTitle");
const captionInput = document.getElementById("caption");
const destinationInput = document.getElementById("destinationUrl");
const previewTitle = document.getElementById("previewTitle");
const previewCaption = document.getElementById("previewCaption");
const destinationDisplay = document.getElementById("destinationDisplay");
const qrColor = document.getElementById("qrColor");
const bgColor = document.getElementById("bgColor");
const qrCard = document.getElementById("qrCard");
const scanLabel = document.getElementById("scanLabel");
const scanLabelToggle = document.getElementById("scanLabelToggle");
const destinationToggle = document.getElementById("destinationToggle");
const sizeInput = document.getElementById("qrSize");
const consentBanner = document.getElementById("consentBanner");
const acceptAnalyticsBtn = document.getElementById("acceptAnalytics");
const declineAnalyticsBtn = document.getElementById("declineAnalytics");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#b42318" : "#2563eb";
}

function normalizeUrl(value) {
  const trimmed = value.trim();
  if (!trimmed) throw new Error("Paste a destination link first.");
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function safeDomain(value) {
  try {
    return new URL(value).hostname.slice(0, 180);
  } catch (_error) {
    return "";
  }
}

function consentId() {
  let value = localStorage.getItem(CONSENT_ID_KEY);
  if (!value) {
    value = `dsqr-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    localStorage.setItem(CONSENT_ID_KEY, value);
  }
  return value;
}

function consentStatus() {
  return localStorage.getItem(CONSENT_CHOICE_KEY) || "";
}

async function postJson(path, payload) {
  try {
    await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (_error) {
    // Analytics must never block QR creation or downloads.
  }
}

function recordConsent(status) {
  localStorage.setItem(CONSENT_CHOICE_KEY, status);
  consentBanner.hidden = true;
  postJson("/api/consent", {
    consent_id: consentId(),
    consent_status: status,
    consent_version: CONSENT_VERSION
  });
  if (status === "accepted") {
    recordEvent("page_loaded");
  }
}

function recordEvent(eventType, extra = {}) {
  if (consentStatus() !== "accepted") return;
  postJson("/api/event", {
    event_type: eventType,
    qr_type: "url",
    design: selectedDesign,
    size: sizeInput.value,
    qr_color: qrColor.value,
    bg_color: bgColor.value,
    consent_status: "accepted",
    ...extra
  });
}

function initConsent() {
  const status = consentStatus();
  if (!status) {
    consentBanner.hidden = false;
    return;
  }
  consentBanner.hidden = true;
  if (status === "accepted") {
    recordEvent("page_loaded");
  }
}

function currentTitle() {
  return titleInput.value.trim() || "Your QR code";
}

function currentCaption() {
  return captionInput.value.trim() || "Ready when you are.";
}

function activePreset(design) {
  selectedDesign = design;
  document.querySelectorAll(".style-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.design === design);
  });

  const preset = presets[design];
  qrColor.value = preset.qr;
  bgColor.value = preset.bg;
  applyPreviewTheme();
  if (latestQr) renderQr(latestQr.smartUrl);
}

function applyPreviewTheme() {
  const preset = presets[selectedDesign];
  qrCard.style.background = preset.card;
  qrCard.style.color = preset.text;
  qrCard.style.borderColor = preset.border;
  qrCard.style.boxShadow = preset.shadow;
  qrCard.style.setProperty("--card-muted", preset.muted);
  qrCard.style.setProperty("--card-accent", preset.accent);
}

function renderQr(smartUrl) {
  qrContainer.innerHTML = "";
  new QRCode(qrContainer, {
    text: smartUrl,
    width: 248,
    height: 248,
    colorDark: qrColor.value,
    colorLight: bgColor.value,
    correctLevel: QRCode.CorrectLevel.H
  });
  emptyState.style.display = "none";
}

function readQrImage() {
  return qrContainer.querySelector("canvas") || qrContainer.querySelector("img") || null;
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function drawWrappedText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  let line = "";
  const lines = [];

  words.forEach((word) => {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = test;
    }
  });

  if (line) lines.push(line);
  lines.slice(0, maxLines).forEach((value, index) => {
    ctx.fillText(value, x, y + index * lineHeight);
  });
}

function updatePreviewText() {
  previewTitle.textContent = currentTitle();
  previewCaption.textContent = currentCaption();
  scanLabel.style.display = scanLabelToggle.checked ? "inline-flex" : "none";
  destinationDisplay.style.display = destinationToggle.checked ? "block" : "none";

  if (latestQr) {
    latestQr.title = currentTitle();
    latestQr.caption = currentCaption();
    latestQr.showScanLabel = scanLabelToggle.checked;
    latestQr.showDestination = destinationToggle.checked;
  }
}

async function downloadCard() {
  if (!latestQr) return;

  await new Promise((resolve) => window.setTimeout(resolve, 120));
  const source = readQrImage();
  if (!source) {
    setStatus("Generate the QR again before downloading.", true);
    return;
  }

  const size = Number(latestQr.size || 720);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = Math.round(size * 1.26);
  const ctx = canvas.getContext("2d");
  const scale = size / 720;
  const preset = presets[selectedDesign];

  ctx.fillStyle = preset.card;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = preset.border;
  ctx.lineWidth = 2 * scale;
  roundRect(ctx, 18 * scale, 18 * scale, canvas.width - 36 * scale, canvas.height - 36 * scale, 26 * scale);
  ctx.stroke();

  ctx.fillStyle = preset.accent;
  roundRect(ctx, 50 * scale, 44 * scale, 72 * scale, 72 * scale, 20 * scale);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.font = `900 ${28 * scale}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.fillText("DS", 86 * scale, 91 * scale);

  ctx.textAlign = "left";
  ctx.fillStyle = preset.text;
  ctx.font = `800 ${19 * scale}px system-ui, sans-serif`;
  ctx.fillText("DS Digital QR", 140 * scale, 68 * scale);
  ctx.font = `800 ${34 * scale}px system-ui, sans-serif`;
  drawWrappedText(ctx, latestQr.title, 140 * scale, 108 * scale, 500 * scale, 40 * scale, 2);
  ctx.fillStyle = preset.muted;
  ctx.font = `600 ${18 * scale}px system-ui, sans-serif`;
  drawWrappedText(ctx, latestQr.caption, 52 * scale, 164 * scale, 616 * scale, 25 * scale, 2);

  if (latestQr.showScanLabel) {
    ctx.fillStyle = preset.accent;
    ctx.font = `900 ${18 * scale}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText("SCAN ME", canvas.width / 2, 238 * scale);
  }

  const qrSize = 444 * scale;
  const qrX = (canvas.width - qrSize) / 2;
  const qrY = 264 * scale;
  ctx.fillStyle = bgColor.value;
  roundRect(ctx, qrX - 26 * scale, qrY - 26 * scale, qrSize + 52 * scale, qrSize + 52 * scale, 30 * scale);
  ctx.fill();
  ctx.drawImage(source, qrX, qrY, qrSize, qrSize);

  ctx.textAlign = "center";
  ctx.fillStyle = preset.text;
  ctx.font = `800 ${18 * scale}px system-ui, sans-serif`;
  ctx.fillText("Free QR code made on dsdigitaldesigns.org", canvas.width / 2, 748 * scale);

  if (latestQr.showDestination) {
    ctx.fillStyle = preset.muted;
    ctx.font = `${14 * scale}px system-ui, sans-serif`;
    drawWrappedText(ctx, latestQr.destination, 72 * scale, 788 * scale, 576 * scale, 22 * scale, 3);
  }

  const link = document.createElement("a");
  link.download = `ds-digital-qr-${latestQr.code}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

function resetGeneratedState() {
  latestQr = null;
  qrContainer.innerHTML = "";
  emptyState.style.display = "block";
  destinationDisplay.textContent = "";
  downloadBtn.disabled = true;
  copyBtn.disabled = true;
  copyBtn.hidden = true;
  setStatus("");
}

document.getElementById("presetGrid").addEventListener("click", (event) => {
  const button = event.target.closest(".style-btn");
  if (!button) return;
  activePreset(button.dataset.design);
  recordEvent("design_selected");
});

[titleInput, captionInput, scanLabelToggle, destinationToggle].forEach((input) => {
  input.addEventListener("input", updatePreviewText);
  input.addEventListener("change", updatePreviewText);
});

destinationInput.addEventListener("input", () => {
  if (latestQr) resetGeneratedState();
});

[qrColor, bgColor].forEach((input) => {
  input.addEventListener("input", () => {
    if (latestQr) renderQr(latestQr.smartUrl);
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  updatePreviewText();
  downloadBtn.disabled = true;
  copyBtn.disabled = true;

  let destinationUrl;
  try {
    destinationUrl = normalizeUrl(destinationInput.value);
  } catch (error) {
    setStatus(error.message, true);
    return;
  }

  const title = currentTitle();
  const caption = currentCaption();
  const size = sizeInput.value;
  setStatus("Creating your QR...");

  try {
    const response = await fetch(`${API_BASE}/api/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        destination_url: destinationUrl,
        title,
        card_title: title,
        caption,
        qr_type: "website",
        design: selectedDesign,
        qr_color: qrColor.value,
        bg_color: bgColor.value,
        size,
        consent_status: consentStatus() || "necessary"
      })
    });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Unable to create QR code.");
    }

    const smartUrl = data.smart_url || `${API_BASE}/q/${encodeURIComponent(data.code)}`;
    latestQr = {
      code: data.code,
      smartUrl,
      destination: destinationUrl,
      title,
      caption,
      size,
      showScanLabel: scanLabelToggle.checked,
      showDestination: destinationToggle.checked
    };

    destinationDisplay.textContent = destinationUrl;
    renderQr(smartUrl);
    applyPreviewTheme();
    updatePreviewText();
    downloadBtn.disabled = false;
    copyBtn.disabled = false;
    copyBtn.hidden = false;
    recordEvent("qr_generated", {
      code: latestQr.code,
      destination_domain: safeDomain(destinationUrl),
      destination_length: destinationUrl.length
    });
    setStatus("QR created. Download your card or copy the smart link.");
  } catch (error) {
    setStatus(error.message || "Could not connect to the QR backend.", true);
  }
});

downloadBtn.addEventListener("click", async () => {
  await downloadCard();
  if (latestQr) {
    recordEvent("qr_downloaded", {
      code: latestQr.code,
      destination_domain: safeDomain(latestQr.destination),
      destination_length: latestQr.destination.length
    });
  }
});

copyBtn.addEventListener("click", async () => {
  if (!latestQr) return;
  await navigator.clipboard.writeText(latestQr.smartUrl);
  recordEvent("smart_link_copied", {
    code: latestQr.code,
    destination_domain: safeDomain(latestQr.destination),
    destination_length: latestQr.destination.length
  });
  setStatus("Smart link copied.");
});

acceptAnalyticsBtn.addEventListener("click", () => recordConsent("accepted"));
declineAnalyticsBtn.addEventListener("click", () => recordConsent("declined"));

activePreset("classic");
updatePreviewText();
initConsent();
