const API_BASE = "https://kali.tail768496.ts.net";
const SMART_TYPES = new Set(["website", "review", "payment"]);

const typeLabels = {
  website: "Website URL",
  text: "Plain Text",
  email: "Email",
  phone: "Phone",
  sms: "SMS",
  wifi: "Wi-Fi",
  contact: "Contact Card",
  event: "Event Details",
  review: "Review Link",
  payment: "Payment Link"
};

const presets = {
  "classic-black": {
    name: "Classic Black",
    qr: "#111827",
    bg: "#ffffff",
    card: "#ffffff",
    text: "#111827",
    muted: "#475467",
    accent: "#111827",
    border: "#d0d5dd",
    shadow: "0 16px 42px rgba(17, 24, 39, 0.12)",
    label: "Classic"
  },
  "ds-purple": {
    name: "DS Purple",
    qr: "#5b21b6",
    bg: "#ffffff",
    card: "#fbf9ff",
    text: "#1f1933",
    muted: "#5d5378",
    accent: "#7c3aed",
    border: "#ddd6fe",
    shadow: "0 20px 52px rgba(124, 58, 237, 0.2)",
    label: "DS Studio"
  },
  "blue-pro": {
    name: "Blue Pro",
    qr: "#1d4ed8",
    bg: "#ffffff",
    card: "#f5f9ff",
    text: "#10233f",
    muted: "#42526b",
    accent: "#2563eb",
    border: "#bfdbfe",
    shadow: "0 18px 46px rgba(37, 99, 235, 0.16)",
    label: "Pro"
  },
  "dark-card": {
    name: "Dark Card",
    qr: "#ffffff",
    bg: "#111827",
    card: "#111827",
    text: "#ffffff",
    muted: "#d1d5db",
    accent: "#60a5fa",
    border: "#293548",
    shadow: "0 24px 60px rgba(0, 0, 0, 0.32)",
    label: "Premium"
  },
  "soft-lavender": {
    name: "Soft Lavender",
    qr: "#6d28d9",
    bg: "#f6f2ff",
    card: "#faf7ff",
    text: "#241238",
    muted: "#6b5f7d",
    accent: "#a78bfa",
    border: "#e9d5ff",
    shadow: "0 18px 48px rgba(109, 40, 217, 0.14)",
    label: "Soft"
  },
  "emerald-fresh": {
    name: "Emerald Fresh",
    qr: "#047857",
    bg: "#f0fdf4",
    card: "#f7fff9",
    text: "#10251e",
    muted: "#4d635b",
    accent: "#10b981",
    border: "#bbf7d0",
    shadow: "0 18px 46px rgba(16, 185, 129, 0.15)",
    label: "Fresh"
  },
  "neon-night": {
    name: "Neon Night",
    qr: "#22d3ee",
    bg: "#020617",
    card: "#070b18",
    text: "#f8fafc",
    muted: "#b6c2d4",
    accent: "#f43f5e",
    border: "#1e293b",
    shadow: "0 26px 70px rgba(244, 63, 94, 0.2)",
    label: "Neon"
  },
  "minimal-white": {
    name: "Minimal White",
    qr: "#0f172a",
    bg: "#ffffff",
    card: "#ffffff",
    text: "#0f172a",
    muted: "#64748b",
    accent: "#64748b",
    border: "#e2e8f0",
    shadow: "0 10px 30px rgba(15, 23, 42, 0.08)",
    label: "Minimal"
  },
  "sticker-style": {
    name: "Sticker Style",
    qr: "#0f172a",
    bg: "#fff7ed",
    card: "#fffbeb",
    text: "#1f2937",
    muted: "#7c5d35",
    accent: "#f59e0b",
    border: "#fbbf24",
    shadow: "0 18px 0 rgba(15, 23, 42, 0.1)",
    label: "Sticker"
  },
  "digital-receipt": {
    name: "Digital Receipt",
    qr: "#14532d",
    bg: "#f7fee7",
    card: "#fcfff4",
    text: "#18230f",
    muted: "#64734f",
    accent: "#65a30d",
    border: "#d9f99d",
    shadow: "0 15px 35px rgba(77, 124, 15, 0.12)",
    label: "Receipt"
  },
  "menu-card": {
    name: "Menu Card",
    qr: "#7f1d1d",
    bg: "#fff7ed",
    card: "#fffaf3",
    text: "#2f1c10",
    muted: "#765a46",
    accent: "#dc2626",
    border: "#fed7aa",
    shadow: "0 18px 44px rgba(220, 38, 38, 0.13)",
    label: "Menu"
  },
  "business-card": {
    name: "Business Card",
    qr: "#0f172a",
    bg: "#f8fafc",
    card: "#f9fafb",
    text: "#111827",
    muted: "#475467",
    accent: "#0f766e",
    border: "#cbd5e1",
    shadow: "0 16px 42px rgba(15, 23, 42, 0.13)",
    label: "Business"
  }
};

let selectedType = "website";
let selectedDesign = "classic-black";
let latestQr = null;

const form = document.getElementById("qrForm");
const dynamicFields = document.getElementById("dynamicFields");
const statusEl = document.getElementById("formStatus");
const qrContainer = document.getElementById("qrcode");
const emptyState = document.getElementById("emptyState");
const downloadBtn = document.getElementById("downloadBtn");
const copyBtn = document.getElementById("copyBtn");
const titleInput = document.getElementById("cardTitle");
const captionInput = document.getElementById("caption");
const previewTitle = document.getElementById("previewTitle");
const previewCaption = document.getElementById("previewCaption");
const destinationDisplay = document.getElementById("destinationDisplay");
const qrColor = document.getElementById("qrColor");
const bgColor = document.getElementById("bgColor");
const qrCard = document.getElementById("qrCard");
const accentLabel = document.getElementById("accentLabel");
const scanLabel = document.getElementById("scanLabel");
const scanLabelToggle = document.getElementById("scanLabelToggle");
const destinationToggle = document.getElementById("destinationToggle");
const modeLabel = document.getElementById("modeLabel");
const modeDescription = document.getElementById("modeDescription");
const modeNoticeTitle = document.getElementById("modeNoticeTitle");
const modeNoticeText = document.getElementById("modeNoticeText");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#b42318" : "#2563eb";
}

function isSmartType() {
  return SMART_TYPES.has(selectedType);
}

function encodeParams(params) {
  return Object.entries(params)
    .filter(([, value]) => value)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join("&");
}

function field(name) {
  const element = form.elements[name];
  return element ? element.value.trim() : "";
}

function normalizeUrl(value) {
  const trimmed = value.trim();
  if (!trimmed) throw new Error("Enter a destination URL.");
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function telValue(value) {
  const trimmed = value.trim();
  if (!trimmed) throw new Error("Enter a phone number.");
  return trimmed;
}

function escapeWifi(value) {
  return value.replaceAll("\\", "\\\\").replaceAll(";", "\\;").replaceAll(",", "\\,").replaceAll(":", "\\:");
}

function compactLines(lines) {
  return lines.filter((line) => line && line.trim()).join("\n");
}

function buildPayload() {
  switch (selectedType) {
    case "website":
      return { content: normalizeUrl(field("destination_url")), display: normalizeUrl(field("destination_url")) };
    case "review":
      return { content: normalizeUrl(field("review_url")), display: normalizeUrl(field("review_url")) };
    case "payment":
      return { content: normalizeUrl(field("payment_url")), display: normalizeUrl(field("payment_url")) };
    case "text": {
      const text = field("plain_text");
      if (!text) throw new Error("Enter text for the QR code.");
      return { content: text, display: "Plain text QR" };
    }
    case "email": {
      const email = field("email_address");
      if (!email) throw new Error("Enter an email address.");
      const params = encodeParams({ subject: field("email_subject"), body: field("email_body") });
      return { content: `mailto:${email}${params ? `?${params}` : ""}`, display: email };
    }
    case "phone": {
      const phone = telValue(field("phone_number"));
      return { content: `tel:${phone}`, display: phone };
    }
    case "sms": {
      const phone = telValue(field("sms_number"));
      const message = field("sms_message");
      return { content: `sms:${phone}${message ? `?body=${encodeURIComponent(message)}` : ""}`, display: phone };
    }
    case "wifi": {
      const ssid = field("wifi_ssid");
      if (!ssid) throw new Error("Enter the Wi-Fi network name.");
      const security = field("wifi_security") || "WPA";
      const password = field("wifi_password");
      const securityPart = security === "nopass" ? "T:nopass;" : `T:${escapeWifi(security)};`;
      const passwordPart = security === "nopass" ? "" : `P:${escapeWifi(password)};`;
      return {
        content: `WIFI:${securityPart}S:${escapeWifi(ssid)};${passwordPart};`,
        display: `${ssid} Wi-Fi`
      };
    }
    case "contact": {
      const name = field("contact_name");
      if (!name) throw new Error("Enter a contact name.");
      const vcard = compactLines([
        "BEGIN:VCARD",
        "VERSION:3.0",
        `FN:${name}`,
        field("contact_company") ? `ORG:${field("contact_company")}` : "",
        field("contact_phone") ? `TEL:${field("contact_phone")}` : "",
        field("contact_email") ? `EMAIL:${field("contact_email")}` : "",
        field("contact_website") ? `URL:${normalizeUrl(field("contact_website"))}` : "",
        "END:VCARD"
      ]);
      return { content: vcard, display: name };
    }
    case "event": {
      const name = field("event_name");
      if (!name) throw new Error("Enter an event name.");
      const eventText = compactLines([
        `Event: ${name}`,
        field("event_location") ? `Location: ${field("event_location")}` : "",
        field("event_datetime") ? `Date/Time: ${field("event_datetime")}` : "",
        field("event_notes") ? `Notes: ${field("event_notes")}` : ""
      ]);
      return { content: eventText, display: name };
    }
    default:
      throw new Error("Choose a QR type.");
  }
}

function renderFields() {
  const templates = {
    website: `
      <div class="field-group">
        <label for="destinationUrl">Destination URL</label>
        <input id="destinationUrl" name="destination_url" type="text" inputmode="url" autocomplete="url" placeholder="example.com/menu" required>
      </div>`,
    text: `
      <div class="field-group">
        <label for="plainText">Text</label>
        <textarea id="plainText" name="plain_text" rows="5" placeholder="Enter the text your QR should open" required></textarea>
      </div>`,
    email: `
      <div class="field-group">
        <label for="emailAddress">Email address</label>
        <input id="emailAddress" name="email_address" type="email" autocomplete="email" placeholder="name@example.com" required>
      </div>
      <div class="field-group">
        <label for="emailSubject">Subject optional</label>
        <input id="emailSubject" name="email_subject" type="text" placeholder="Question about your services">
      </div>
      <div class="field-group">
        <label for="emailBody">Body optional</label>
        <textarea id="emailBody" name="email_body" rows="3" placeholder="Hi, I would like to..."></textarea>
      </div>`,
    phone: `
      <div class="field-group">
        <label for="phoneNumber">Phone number</label>
        <input id="phoneNumber" name="phone_number" type="tel" autocomplete="tel" placeholder="+15555555555" required>
      </div>`,
    sms: `
      <div class="field-group">
        <label for="smsNumber">Phone number</label>
        <input id="smsNumber" name="sms_number" type="tel" autocomplete="tel" placeholder="+15555555555" required>
      </div>
      <div class="field-group">
        <label for="smsMessage">Message</label>
        <textarea id="smsMessage" name="sms_message" rows="3" placeholder="I would like to book an appointment."></textarea>
      </div>`,
    wifi: `
      <div class="field-group">
        <label for="wifiSsid">Network name</label>
        <input id="wifiSsid" name="wifi_ssid" type="text" autocomplete="off" placeholder="Cafe Guest" required>
      </div>
      <div class="field-group">
        <label for="wifiPassword">Password</label>
        <input id="wifiPassword" name="wifi_password" type="text" autocomplete="off" placeholder="guest-password">
      </div>
      <div class="field-group">
        <label for="wifiSecurity">Security type</label>
        <select id="wifiSecurity" name="wifi_security">
          <option value="WPA" selected>WPA/WPA2</option>
          <option value="WEP">WEP</option>
          <option value="nopass">No password</option>
        </select>
      </div>`,
    contact: `
      <div class="field-group">
        <label for="contactName">Name</label>
        <input id="contactName" name="contact_name" type="text" autocomplete="name" placeholder="Dylan Sprouse" required>
      </div>
      <div class="split-row">
        <div class="field-group">
          <label for="contactPhone">Phone</label>
          <input id="contactPhone" name="contact_phone" type="tel" autocomplete="tel" placeholder="+15555555555">
        </div>
        <div class="field-group">
          <label for="contactEmail">Email</label>
          <input id="contactEmail" name="contact_email" type="email" autocomplete="email" placeholder="name@example.com">
        </div>
      </div>
      <div class="split-row">
        <div class="field-group">
          <label for="contactWebsite">Website</label>
          <input id="contactWebsite" name="contact_website" type="text" inputmode="url" autocomplete="url" placeholder="example.com">
        </div>
        <div class="field-group">
          <label for="contactCompany">Company</label>
          <input id="contactCompany" name="contact_company" type="text" autocomplete="organization" placeholder="DS Digital Designs">
        </div>
      </div>`,
    event: `
      <div class="field-group">
        <label for="eventName">Event name</label>
        <input id="eventName" name="event_name" type="text" placeholder="Grand opening" required>
      </div>
      <div class="field-group">
        <label for="eventLocation">Location</label>
        <input id="eventLocation" name="event_location" type="text" placeholder="123 Main Street">
      </div>
      <div class="field-group">
        <label for="eventDatetime">Date/time</label>
        <input id="eventDatetime" name="event_datetime" type="datetime-local">
      </div>
      <div class="field-group">
        <label for="eventNotes">Notes</label>
        <textarea id="eventNotes" name="event_notes" rows="3" placeholder="Bring your confirmation email."></textarea>
      </div>`,
    review: `
      <div class="field-group">
        <label for="reviewUrl">Review URL</label>
        <input id="reviewUrl" name="review_url" type="text" inputmode="url" autocomplete="url" placeholder="g.page/r/your-review-link" required>
      </div>`,
    payment: `
      <div class="field-group">
        <label for="paymentUrl">Payment URL</label>
        <input id="paymentUrl" name="payment_url" type="text" inputmode="url" autocomplete="url" placeholder="square.link/u/example" required>
      </div>`
  };

  dynamicFields.innerHTML = templates[selectedType];
  updateModeUi();
}

function updateModeUi() {
  if (isSmartType()) {
    modeLabel.textContent = "Smart Link mode";
    modeDescription.textContent = "Creates a backend record, tracks scans, and encodes the DS smart link.";
    modeNoticeTitle.textContent = "Smart Link mode tracks scans.";
    modeNoticeText.textContent = "Generated smart QR links point directly to https://kali.tail768496.ts.net/q/<code>.";
  } else {
    modeLabel.textContent = "Static QR mode";
    modeDescription.textContent = "No backend record is created. The QR directly encodes the content.";
    modeNoticeTitle.textContent = "Static QR codes do not use the DS redirect or scan tracking.";
    modeNoticeText.textContent = "They still download as DS-branded QR cards with the footer included.";
  }
}

function activeType(type) {
  selectedType = type;
  document.querySelectorAll(".type-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.type === type);
  });
  renderFields();
  clearGeneratedState(false);
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
  if (latestQr) renderQr(latestQr.content);
}

function applyPreviewTheme() {
  const preset = presets[selectedDesign];
  qrCard.style.background = preset.card;
  qrCard.style.color = preset.text;
  qrCard.style.borderColor = preset.border;
  qrCard.style.boxShadow = preset.shadow;
  qrCard.style.setProperty("--card-muted", preset.muted);
  qrCard.style.setProperty("--card-accent", preset.accent);
  accentLabel.textContent = preset.label;
  accentLabel.style.background = preset.accent;
  accentLabel.style.color = selectedDesign === "soft-lavender" || selectedDesign === "sticker-style" ? "#111827" : "#ffffff";
}

function renderQr(content) {
  qrContainer.innerHTML = "";
  new QRCode(qrContainer, {
    text: content,
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
  lines.slice(0, maxLines).forEach((value, index) => {
    ctx.fillText(value, x, y + index * lineHeight);
  });
}

function currentTitle() {
  return titleInput.value.trim() || `${typeLabels[selectedType]} QR code`;
}

function currentCaption() {
  return captionInput.value.trim() || (isSmartType() ? "Smart DS redirect with scan tracking." : "Static QR code. No redirect or scan tracking.");
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
  canvas.height = Math.round(size * 1.32);
  const ctx = canvas.getContext("2d");
  const scale = size / 720;
  const preset = presets[selectedDesign];

  ctx.fillStyle = preset.card;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = preset.border;
  ctx.lineWidth = 2 * scale;
  roundRect(ctx, 18 * scale, 18 * scale, canvas.width - 36 * scale, canvas.height - 36 * scale, 28 * scale);
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
  drawWrappedText(ctx, latestQr.caption, 52 * scale, 168 * scale, 616 * scale, 25 * scale, 2);

  if (latestQr.showScanLabel) {
    ctx.fillStyle = preset.accent;
    ctx.font = `900 ${18 * scale}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText("SCAN ME", canvas.width / 2, 247 * scale);
  }

  const qrSize = 444 * scale;
  const qrX = (canvas.width - qrSize) / 2;
  const qrY = 278 * scale;
  ctx.fillStyle = bgColor.value;
  roundRect(ctx, qrX - 26 * scale, qrY - 26 * scale, qrSize + 52 * scale, qrSize + 52 * scale, 30 * scale);
  ctx.fill();
  ctx.drawImage(source, qrX, qrY, qrSize, qrSize);

  ctx.textAlign = "center";
  ctx.fillStyle = preset.text;
  ctx.font = `800 ${18 * scale}px system-ui, sans-serif`;
  ctx.fillText("Free QR code made on dsdigitaldesigns.org", canvas.width / 2, 780 * scale);

  if (latestQr.showDestination) {
    ctx.fillStyle = preset.muted;
    ctx.font = `${14 * scale}px system-ui, sans-serif`;
    drawWrappedText(ctx, latestQr.display, 72 * scale, 820 * scale, 576 * scale, 22 * scale, 3);
  }

  const link = document.createElement("a");
  link.download = `ds-digital-qr-${latestQr.code || selectedType}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

function clearGeneratedState(clearInputs = true) {
  latestQr = null;
  qrContainer.innerHTML = "";
  emptyState.style.display = "block";
  destinationDisplay.textContent = isSmartType() ? "https://kali.tail768496.ts.net/q/..." : "Static QR content preview";
  downloadBtn.disabled = true;
  copyBtn.disabled = true;
  if (clearInputs) {
    form.reset();
    activePreset("classic-black");
    renderFields();
  }
  updatePreviewText();
  setStatus("");
}

document.getElementById("typeGrid").addEventListener("click", (event) => {
  const button = event.target.closest(".type-btn");
  if (!button) return;
  activeType(button.dataset.type);
});

document.getElementById("presetGrid").addEventListener("click", (event) => {
  const button = event.target.closest(".preset-btn");
  if (!button) return;
  activePreset(button.dataset.design);
});

[titleInput, captionInput, scanLabelToggle, destinationToggle].forEach((input) => {
  input.addEventListener("input", updatePreviewText);
  input.addEventListener("change", updatePreviewText);
});

[qrColor, bgColor].forEach((input) => {
  input.addEventListener("input", () => {
    if (latestQr) renderQr(latestQr.content);
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  updatePreviewText();
  downloadBtn.disabled = true;
  copyBtn.disabled = true;

  try {
    const built = buildPayload();
    const size = form.elements.size.value;
    const title = currentTitle();
    const caption = currentCaption();

    if (isSmartType()) {
      setStatus("Creating your smart QR...");
      const response = await fetch(`${API_BASE}/api/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          destination_url: built.content,
          title,
          card_title: title,
          caption,
          qr_type: selectedType,
          design: selectedDesign,
          qr_color: qrColor.value,
          bg_color: bgColor.value,
          size
        })
      });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.error || "Unable to create QR code.");
      }

      const smartUrl = data.smart_url || `${API_BASE}/q/${encodeURIComponent(data.code)}`;
      latestQr = {
        code: data.code,
        content: smartUrl,
        smartUrl,
        display: smartUrl,
        rawDestination: built.content,
        title,
        caption,
        size,
        mode: "smart",
        showScanLabel: scanLabelToggle.checked,
        showDestination: destinationToggle.checked
      };
      destinationDisplay.textContent = smartUrl;
      copyBtn.disabled = false;
      setStatus("Smart QR created. You can copy the smart link or download the PNG.");
    } else {
      latestQr = {
        code: selectedType,
        content: built.content,
        display: built.display,
        title,
        caption,
        size,
        mode: "static",
        showScanLabel: scanLabelToggle.checked,
        showDestination: destinationToggle.checked
      };
      destinationDisplay.textContent = built.display;
      setStatus("Static QR created. Static QR codes do not use the DS redirect or scan tracking.");
    }

    previewTitle.textContent = latestQr.title;
    previewCaption.textContent = latestQr.caption;
    renderQr(latestQr.content);
    applyPreviewTheme();
    downloadBtn.disabled = false;
  } catch (error) {
    setStatus(error.message || "Could not create the QR code.", true);
  }
});

downloadBtn.addEventListener("click", downloadCard);

copyBtn.addEventListener("click", async () => {
  if (!latestQr || latestQr.mode !== "smart") return;
  await navigator.clipboard.writeText(latestQr.smartUrl);
  setStatus("Smart link copied.");
});

document.getElementById("clearBtn").addEventListener("click", () => {
  clearGeneratedState(true);
});

renderFields();
activePreset("classic-black");
updatePreviewText();
