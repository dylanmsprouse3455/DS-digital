const API_BASE = "https://kali.tail768496.ts.net"; // For production, replace with your public tunnel/backend URL.

const presets = {
  classic: { qr: "#111827", bg: "#ffffff", card: "#ffffff", accent: "#2563eb", text: "#111827" },
  "ds-purple": { qr: "#5b21b6", bg: "#ffffff", card: "#fbf9ff", accent: "#7c3aed", text: "#111827" },
  "blue-pro": { qr: "#1d4ed8", bg: "#ffffff", card: "#f5f9ff", accent: "#2563eb", text: "#111827" },
  "dark-card": { qr: "#ffffff", bg: "#111827", card: "#111827", accent: "#60a5fa", text: "#ffffff" },
  "soft-card": { qr: "#344054", bg: "#f8fafc", card: "#f8fafc", accent: "#7c3aed", text: "#111827" }
};

let selectedDesign = "classic";
let latestQr = null;

const form = document.getElementById("qrForm");
const statusEl = document.getElementById("formStatus");
const qrContainer = document.getElementById("qrcode");
const emptyState = document.getElementById("emptyState");
const downloadBtn = document.getElementById("downloadBtn");
const titleInput = document.getElementById("cardTitle");
const previewTitle = document.getElementById("previewTitle");
const smartUrlText = document.getElementById("smartUrlText");
const qrColor = document.getElementById("qrColor");
const bgColor = document.getElementById("bgColor");
const qrCard = document.getElementById("qrCard");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#b42318" : "#2563eb";
}

function activePreset(design) {
  selectedDesign = design;
  document.querySelectorAll(".preset-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.design === design);
  });
  const preset = presets[design];
  qrColor.value = preset.qr;
  bgColor.value = preset.bg;
  applyPreviewTheme();
}

function applyPreviewTheme() {
  const preset = presets[selectedDesign];
  qrCard.style.background = preset.card;
  qrCard.style.color = preset.text;
  qrCard.style.borderColor = selectedDesign === "dark-card" ? "#293548" : "#e5e7eb";
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
  const canvas = qrContainer.querySelector("canvas");
  if (canvas) {
    return canvas;
  }

  const image = qrContainer.querySelector("img");
  return image || null;
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
  const words = text.split(/\s+/).filter(Boolean);
  let line = "";
  let lines = [];

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
  lines = lines.slice(0, maxLines);
  lines.forEach((value, index) => ctx.fillText(value, x, y + index * lineHeight));
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
  canvas.height = Math.round(size * 1.28);
  const ctx = canvas.getContext("2d");
  const scale = size / 720;
  const preset = presets[selectedDesign];

  ctx.fillStyle = preset.card;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.save();
  ctx.fillStyle = preset.accent;
  roundRect(ctx, 48 * scale, 44 * scale, 70 * scale, 70 * scale, 22 * scale);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.font = `${28 * scale}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.fillText("DS", 83 * scale, 90 * scale);
  ctx.restore();

  ctx.textAlign = "left";
  ctx.fillStyle = preset.text;
  ctx.font = `800 ${20 * scale}px system-ui, sans-serif`;
  ctx.fillText("DS Digital QR", 136 * scale, 70 * scale);
  ctx.font = `700 ${34 * scale}px system-ui, sans-serif`;
  drawWrappedText(ctx, latestQr.title || "Your smart QR code", 136 * scale, 108 * scale, 500 * scale, 40 * scale, 2);

  const qrSize = 456 * scale;
  const qrX = (canvas.width - qrSize) / 2;
  const qrY = 185 * scale;
  ctx.fillStyle = bgColor.value;
  roundRect(ctx, qrX - 24 * scale, qrY - 24 * scale, qrSize + 48 * scale, qrSize + 48 * scale, 30 * scale);
  ctx.fill();
  ctx.drawImage(source, qrX, qrY, qrSize, qrSize);

  ctx.textAlign = "center";
  ctx.fillStyle = selectedDesign === "dark-card" ? "#d1d5db" : "#475467";
  ctx.font = `700 ${18 * scale}px system-ui, sans-serif`;
  ctx.fillText("Free QR code made on dsdigitaldesigns.org", canvas.width / 2, 705 * scale);
  ctx.font = `${14 * scale}px system-ui, sans-serif`;
  drawWrappedText(ctx, latestQr.smartUrl, 72 * scale, 746 * scale, 576 * scale, 22 * scale, 3);

  const link = document.createElement("a");
  link.download = `ds-digital-qr-${latestQr.code}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

document.getElementById("presetGrid").addEventListener("click", (event) => {
  const button = event.target.closest(".preset-btn");
  if (!button) return;
  activePreset(button.dataset.design);
});

titleInput.addEventListener("input", () => {
  previewTitle.textContent = titleInput.value.trim() || "Your smart QR code";
});

[qrColor, bgColor].forEach((input) => {
  input.addEventListener("input", () => {
    if (latestQr) renderQr(latestQr.smartUrl);
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Creating your smart QR...");
  downloadBtn.disabled = true;

  const formData = new FormData(form);
  const payload = {
    destination_url: formData.get("destination_url"),
    title: formData.get("title"),
    design: selectedDesign,
    qr_color: formData.get("qr_color"),
    bg_color: formData.get("bg_color"),
    size: formData.get("size")
  };

  try {
    const response = await fetch(`${API_BASE}/api/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Unable to create QR code.");
    }

    const smartUrl = data.smart_url || `${API_BASE}/q/${encodeURIComponent(data.code)}`;
    latestQr = {
      code: data.code,
      smartUrl,
      title: payload.title || "Your smart QR code",
      size: payload.size
    };

    previewTitle.textContent = latestQr.title;
    smartUrlText.textContent = smartUrl;
    renderQr(smartUrl);
    applyPreviewTheme();
    downloadBtn.disabled = false;
    setStatus("Smart QR created. You can download the PNG now.");
  } catch (error) {
    setStatus(error.message || "Could not connect to the QR backend.", true);
  }
});

downloadBtn.addEventListener("click", downloadCard);
activePreset("classic");
