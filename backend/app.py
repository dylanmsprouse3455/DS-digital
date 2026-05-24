import secrets
import sqlite3
import string
from hmac import compare_digest
from datetime import datetime, timezone
from os import environ
from pathlib import Path
from urllib.parse import urlparse

from flask import g, jsonify, redirect, render_template_string, request, session
from flask import Flask
from flask_cors import CORS


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "ds_smart_qr.db"
PUBLIC_SMART_BASE = environ.get("PUBLIC_SMART_BASE", "https://kali.tail768496.ts.net").rstrip("/")
ADMIN_PASSWORD = environ.get("ADMIN_PASSWORD", "")
SECRET_KEY = environ.get("SECRET_KEY") or secrets.token_urlsafe(32)
ALPHABET = string.ascii_letters + string.digits
CONSENT_VERSION = "2026-05-24"
SAFE_EVENT_TYPES = {
    "page_loaded",
    "design_selected",
    "qr_generated",
    "qr_downloaded",
    "smart_link_copied",
    "qr_created",
    "qr_scanned",
}

app = Flask(__name__)
# Production should set SECRET_KEY in the service environment so admin sessions
# survive restarts and are signed with a stable private value.
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://dsdigitaldesigns.org",
                "http://127.0.0.1:5051",
                "http://localhost:5051",
                "null",
            ]
        }
    },
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS qr_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            destination_url TEXT NOT NULL,
            title TEXT,
            design TEXT,
            qr_color TEXT,
            bg_color TEXT,
            size TEXT,
            qr_type TEXT,
            card_title TEXT,
            caption TEXT,
            destination_domain TEXT,
            last_scanned_at TEXT,
            created_at TEXT,
            scan_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS qr_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            scanned_at TEXT NOT NULL,
            user_agent TEXT,
            referrer TEXT,
            ip_address TEXT
        );

        CREATE TABLE IF NOT EXISTS qr_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            code TEXT,
            created_at TEXT NOT NULL,
            qr_type TEXT,
            design TEXT,
            size TEXT,
            qr_color TEXT,
            bg_color TEXT,
            destination_domain TEXT,
            destination_length INTEGER,
            user_agent TEXT,
            referrer TEXT,
            ip_address TEXT,
            consent_status TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS consent_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            consent_id TEXT,
            consent_status TEXT NOT NULL,
            consent_version TEXT NOT NULL,
            user_agent TEXT,
            ip_address TEXT
        );
        """
    )
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(qr_links)").fetchall()
    }
    optional_columns = {
        "qr_type": "TEXT",
        "design": "TEXT",
        "qr_color": "TEXT",
        "bg_color": "TEXT",
        "size": "TEXT",
        "card_title": "TEXT",
        "caption": "TEXT",
        "destination_domain": "TEXT",
        "last_scanned_at": "TEXT",
    }
    for column, column_type in optional_columns.items():
        if column not in existing_columns:
            db.execute(f"ALTER TABLE qr_links ADD COLUMN {column} {column_type}")
    db.commit()


def normalize_url(raw_url):
    if not raw_url or not str(raw_url).strip():
        raise ValueError("Destination URL is required.")

    value = str(raw_url).strip()
    if not value.lower().startswith(("http://", "https://")):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid destination URL.")

    return value


def destination_domain(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    return (parsed.netloc or "").lower()[:180]


def clean_text(value, max_length):
    if value is None:
        return ""
    return str(value).strip()[:max_length]


def clean_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def user_agent_summary(value):
    value = clean_text(value, 240)
    if not value:
        return ""
    for marker in (" Chrome/", " Safari/", " Firefox/", " Edg/", " Version/"):
        value = value.replace(marker, f"\n{marker.strip()}")
    return value.split("\n", 1)[0][:160]


def generate_code():
    db = get_db()
    for length in (6, 7, 8):
        for _ in range(12):
            code = "".join(secrets.choice(ALPHABET) for _ in range(length))
            exists = db.execute("SELECT 1 FROM qr_links WHERE code = ?", (code,)).fetchone()
            if not exists:
                return code
    raise RuntimeError("Could not generate a unique QR code.")


def request_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or ""


def log_event(
    db,
    event_type,
    code="",
    qr_type="",
    design="",
    size="",
    qr_color="",
    bg_color="",
    domain="",
    destination_length=0,
    consent_status="necessary",
    notes="",
):
    if event_type not in SAFE_EVENT_TYPES:
        return
    db.execute(
        """
        INSERT INTO qr_events (
            event_type, code, created_at, qr_type, design, size, qr_color, bg_color,
            destination_domain, destination_length, user_agent, referrer, ip_address,
            consent_status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            clean_text(code, 12),
            utc_now(),
            clean_text(qr_type, 40),
            clean_text(design, 30),
            clean_text(size, 12),
            clean_text(qr_color, 20),
            clean_text(bg_color, 20),
            clean_text(domain, 180),
            clean_int(destination_length),
            clean_text(request.headers.get("User-Agent", ""), 500),
            clean_text(request.headers.get("Referer", ""), 500),
            request_ip(),
            clean_text(consent_status, 20),
            clean_text(notes, 240),
        ),
    )


def record_scan(db, code):
    scanned_at = utc_now()
    row = db.execute(
        "SELECT destination_url, destination_domain, qr_type, design, size, qr_color, bg_color FROM qr_links WHERE code = ?",
        (code,),
    ).fetchone()
    db.execute(
        "UPDATE qr_links SET scan_count = scan_count + 1, last_scanned_at = ? WHERE code = ?",
        (scanned_at, code),
    )
    db.execute(
        """
        INSERT INTO qr_scans (code, scanned_at, user_agent, referrer, ip_address)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            code,
            scanned_at,
            request.headers.get("User-Agent", ""),
            request.headers.get("Referer", ""),
            request_ip(),
        ),
    )
    if row:
        domain = row["destination_domain"] or destination_domain(row["destination_url"])
        log_event(
            db,
            "qr_scanned",
            code=code,
            qr_type=row["qr_type"] or "website",
            design=row["design"] or "",
            size=row["size"] or "",
            qr_color=row["qr_color"] or "",
            bg_color=row["bg_color"] or "",
            domain=domain,
            destination_length=len(row["destination_url"] or ""),
            consent_status="necessary",
        )
    db.commit()


@app.before_request
def ensure_database():
    init_db()


@app.get("/")
def home():
    return redirect("/admin")


@app.post("/api/create")
def create_qr():
    data = request.get_json(silent=True) or {}

    try:
        destination_url = normalize_url(data.get("destination_url"))
        code = generate_code()
    except ValueError as error:
        return jsonify(ok=False, error=str(error)), 400
    except RuntimeError as error:
        return jsonify(ok=False, error=str(error)), 500

    title = clean_text(data.get("title"), 80)
    card_title = clean_text(data.get("card_title") or title, 80)
    caption = clean_text(data.get("caption"), 180)
    qr_type = clean_text(data.get("qr_type") or "website", 40)
    design = clean_text(data.get("design"), 30)
    qr_color = clean_text(data.get("qr_color"), 20)
    bg_color = clean_text(data.get("bg_color"), 20)
    size = clean_text(data.get("size"), 12)
    domain = destination_domain(destination_url)
    destination_length = len(destination_url)
    consent_status = clean_text(data.get("consent_status") or "necessary", 20)

    db = get_db()
    db.execute(
        """
        INSERT INTO qr_links
            (code, destination_url, title, design, qr_color, bg_color, size, qr_type, card_title, caption, destination_domain, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            code,
            destination_url,
            title,
            design,
            qr_color,
            bg_color,
            size,
            qr_type,
            card_title,
            caption,
            domain,
            utc_now(),
        ),
    )
    log_event(
        db,
        "qr_created",
        code=code,
        qr_type=qr_type,
        design=design,
        size=size,
        qr_color=qr_color,
        bg_color=bg_color,
        domain=domain,
        destination_length=destination_length,
        consent_status=consent_status or "necessary",
    )
    db.commit()

    return jsonify(
        ok=True,
        code=code,
        smart_url=f"{PUBLIC_SMART_BASE}/q/{code}",
        destination_url=destination_url,
    )


@app.post("/api/consent")
def record_consent():
    data = request.get_json(silent=True) or {}
    consent_status = clean_text(data.get("consent_status"), 20)
    if consent_status not in {"accepted", "declined"}:
        return jsonify(ok=False, error="Consent status must be accepted or declined."), 400

    consent_version = clean_text(data.get("consent_version") or CONSENT_VERSION, 40)
    consent_id = clean_text(data.get("consent_id"), 80)
    db = get_db()
    db.execute(
        """
        INSERT INTO consent_records
            (created_at, consent_id, consent_status, consent_version, user_agent, ip_address)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now(),
            consent_id,
            consent_status,
            consent_version,
            clean_text(request.headers.get("User-Agent", ""), 500),
            request_ip(),
        ),
    )
    db.commit()
    return jsonify(ok=True)


@app.post("/api/event")
def record_frontend_event():
    data = request.get_json(silent=True) or {}
    event_type = clean_text(data.get("event_type"), 40)
    consent_status = clean_text(data.get("consent_status"), 20)

    if consent_status != "accepted":
        return jsonify(ok=False, error="Analytics consent is required for optional events."), 403
    if event_type not in SAFE_EVENT_TYPES - {"qr_created", "qr_scanned"}:
        return jsonify(ok=False, error="Unsupported event type."), 400

    db = get_db()
    log_event(
        db,
        event_type,
        code=data.get("code"),
        qr_type=data.get("qr_type"),
        design=data.get("design"),
        size=data.get("size"),
        qr_color=data.get("qr_color"),
        bg_color=data.get("bg_color"),
        domain=data.get("destination_domain"),
        destination_length=data.get("destination_length"),
        consent_status=consent_status,
        notes=data.get("notes"),
    )
    db.commit()
    return jsonify(ok=True)


@app.get("/q/<code>")
def smart_redirect(code):
    clean_code = clean_text(code, 12)
    db = get_db()
    row = db.execute("SELECT * FROM qr_links WHERE code = ?", (clean_code,)).fetchone()

    if row is None:
        return (
            render_template_string(
                REDIRECT_TEMPLATE,
                found=False,
                destination_url="",
                title="QR code not found",
            ),
            404,
        )

    record_scan(db, clean_code)

    return render_template_string(
        REDIRECT_TEMPLATE,
        found=True,
        destination_url=row["destination_url"],
        title=row["title"] or row["destination_url"],
    )


@app.get("/api/resolve/<code>")
def resolve_qr(code):
    clean_code = clean_text(code, 12)
    db = get_db()
    row = db.execute("SELECT * FROM qr_links WHERE code = ?", (clean_code,)).fetchone()

    if row is None:
        return jsonify(ok=False, error="QR code not found."), 404

    record_scan(db, clean_code)

    return jsonify(
        ok=True,
        destination_url=row["destination_url"],
        title=row["title"] or "",
        code=row["code"],
    )


REDIRECT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <title>{% if found %}Redirecting{% else %}QR code not found{% endif %} | DS Digital QR</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #111827;
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.18), transparent 32rem),
        linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
    }
    main {
      width: min(520px, 100%);
      padding: 32px;
      border: 1px solid rgba(148, 163, 184, 0.34);
      border-radius: 24px;
      background: rgba(255, 255, 255, 0.92);
      box-shadow: 0 24px 70px rgba(15, 23, 42, 0.16);
      text-align: center;
    }
    .badge {
      display: inline-grid;
      place-items: center;
      width: 68px;
      height: 68px;
      margin-bottom: 18px;
      border-radius: 18px;
      color: #ffffff;
      background: #2563eb;
      font-size: 24px;
      font-weight: 900;
      letter-spacing: 0;
    }
    .brand { margin: 0 0 8px; color: #475467; font-size: 14px; font-weight: 800; text-transform: uppercase; }
    h1 { margin: 0; font-size: clamp(30px, 8vw, 44px); line-height: 1.05; letter-spacing: 0; }
    .message { margin: 16px auto 0; max-width: 34rem; color: #475467; font-size: 16px; line-height: 1.6; }
    .url {
      display: block;
      margin: 18px 0 0;
      padding: 12px 14px;
      border: 1px solid #dbe3ef;
      border-radius: 12px;
      color: #1d4ed8;
      background: #f8fafc;
      font-size: 14px;
      overflow-wrap: anywhere;
      text-decoration: none;
    }
    .track {
      height: 8px;
      margin: 24px 0 18px;
      overflow: hidden;
      border-radius: 999px;
      background: #e5e7eb;
    }
    .bar {
      display: block;
      height: 100%;
      width: 100%;
      transform-origin: left;
      background: linear-gradient(90deg, #2563eb, #7c3aed);
      animation: fill 3.8s ease-out forwards;
    }
    .continue { color: #2563eb; font-weight: 800; }
    .muted { color: #64748b; }
    @keyframes fill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
    @media (max-width: 520px) { main { padding: 26px 20px; border-radius: 18px; } }
  </style>
</head>
<body>
  <main>
    <span class="badge">DS</span>
    <p class="brand">DS Digital Designs</p>
    {% if found %}
      <h1>Redirecting you now...</h1>
      <p class="message">This QR code was created with DS Digital QR on dsdigitaldesigns.org.</p>
      <a class="url" href="{{ destination_url }}" rel="nofollow">{{ destination_url }}</a>
      <div class="track" aria-hidden="true"><span class="bar"></span></div>
      <a class="continue" href="{{ destination_url }}" rel="nofollow">Continue now</a>
      <script>
        window.setTimeout(() => {
          window.location.href = {{ destination_url|tojson }};
        }, 3800);
      </script>
    {% else %}
      <h1>QR code not found</h1>
      <p class="message">This smart QR link is missing, inactive, or unavailable.</p>
      <p class="muted">Please check the QR code or contact DS Digital Designs.</p>
    {% endif %}
  </main>
</body>
</html>
"""


ADMIN_AUTH_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <title>{% if missing_password %}Admin Not Configured{% else %}Admin Login{% endif %} | DS Digital QR</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #111827;
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.16), transparent 30rem),
        linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
    }
    main {
      width: min(430px, 100%);
      padding: 28px;
      border: 1px solid #dbe3ef;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.95);
      box-shadow: 0 24px 70px rgba(15, 23, 42, 0.14);
    }
    .badge {
      width: 58px;
      height: 58px;
      display: inline-grid;
      place-items: center;
      margin-bottom: 16px;
      border-radius: 16px;
      color: #ffffff;
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      font-weight: 900;
    }
    p { margin: 10px 0 0; color: #64748b; line-height: 1.55; }
    h1 { margin: 0; font-size: 32px; letter-spacing: 0; }
    label { display: block; margin-top: 20px; color: #344054; font-size: 14px; font-weight: 850; }
    input {
      width: 100%;
      min-height: 50px;
      margin-top: 8px;
      padding: 12px 13px;
      border: 1px solid #d0d5dd;
      border-radius: 12px;
      font: inherit;
    }
    button {
      width: 100%;
      min-height: 50px;
      margin-top: 16px;
      border: 0;
      border-radius: 12px;
      color: white;
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      font: inherit;
      font-weight: 900;
      cursor: pointer;
    }
    .error {
      padding: 10px 12px;
      border: 1px solid #fecaca;
      border-radius: 12px;
      color: #991b1b;
      background: #fef2f2;
      font-weight: 800;
    }
    .warning {
      padding: 12px;
      border: 1px solid #fed7aa;
      border-radius: 12px;
      color: #9a3412;
      background: #fff7ed;
      font-weight: 800;
    }
  </style>
</head>
<body>
  <main>
    <span class="badge">DS</span>
    {% if missing_password %}
      <h1>Admin password is not configured.</h1>
      <p class="warning">ADMIN_PASSWORD must be set on the server before the admin dashboard can be viewed.</p>
      <p>Set ADMIN_PASSWORD and SECRET_KEY in the ds-digital-qr systemd service environment, then restart the service.</p>
    {% else %}
      <h1>Admin Login</h1>
      <p>Enter the DS Digital QR admin password to view QR records and analytics.</p>
      {% if error %}<p class="error">{{ error }}</p>{% endif %}
      <form method="post" action="/admin">
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
        <button type="submit">Login</button>
      </form>
    {% endif %}
  </main>
</body>
</html>
"""


@app.route("/admin", methods=["GET", "POST"])
def admin():
    # TODO: Keep /admin password-protected before public promotion.
    if not ADMIN_PASSWORD:
        session.pop("admin_authenticated", None)
        return render_template_string(ADMIN_AUTH_TEMPLATE, missing_password=True, error=""), 503

    error = ""
    if request.method == "POST":
        password = request.form.get("password", "")
        if compare_digest(password, ADMIN_PASSWORD):
            session["admin_authenticated"] = True
            return redirect("/admin")
        error = "Incorrect password."

    if not session.get("admin_authenticated"):
        return render_template_string(
            ADMIN_AUTH_TEMPLATE,
            missing_password=False,
            error=error,
        )

    db = get_db()
    today = utc_now()[:10]
    overview = {
        "total_qr": db.execute("SELECT COUNT(*) AS value FROM qr_links").fetchone()["value"],
        "total_scans": db.execute("SELECT COALESCE(SUM(scan_count), 0) AS value FROM qr_links").fetchone()["value"],
        "scans_today": db.execute(
            "SELECT COUNT(*) AS value FROM qr_scans WHERE substr(scanned_at, 1, 10) = ?",
            (today,),
        ).fetchone()["value"],
        "created_today": db.execute(
            "SELECT COUNT(*) AS value FROM qr_links WHERE substr(created_at, 1, 10) = ?",
            (today,),
        ).fetchone()["value"],
        "top_design": (
            db.execute(
                """
                SELECT COALESCE(NULLIF(design, ''), 'Unknown') AS value, COUNT(*) AS count
                FROM qr_links
                GROUP BY value
                ORDER BY count DESC
                LIMIT 1
                """
            ).fetchone()
            or {"value": ""}
        )["value"],
        "top_domain": (
            db.execute(
                """
                SELECT COALESCE(NULLIF(destination_domain, ''), 'Unknown') AS value, COUNT(*) AS count
                FROM qr_links
                GROUP BY value
                ORDER BY count DESC
                LIMIT 1
                """
            ).fetchone()
            or {"value": ""}
        )["value"],
    }
    qr_rows = db.execute(
        """
        SELECT
            q.code,
            q.destination_url,
            q.destination_domain,
            q.title,
            q.qr_type,
            q.design,
            q.created_at,
            q.scan_count,
            q.last_scanned_at,
            MAX(s.scanned_at) AS scan_last_scanned
        FROM qr_links q
        LEFT JOIN qr_scans s ON s.code = q.code
        GROUP BY q.id
        ORDER BY q.id DESC
        LIMIT 200
        """
    ).fetchall()
    recent_scans = db.execute(
        """
        SELECT
            s.scanned_at,
            s.code,
            COALESCE(q.destination_domain, '') AS destination_domain,
            s.user_agent,
            s.referrer,
            s.ip_address
        FROM qr_scans s
        LEFT JOIN qr_links q ON q.code = s.code
        ORDER BY s.id DESC
        LIMIT 100
        """
    ).fetchall()
    recent_events = db.execute(
        """
        SELECT created_at, event_type, code, qr_type, design, consent_status
        FROM qr_events
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()
    consent_rows = db.execute(
        """
        SELECT created_at, consent_status, consent_version, user_agent, ip_address
        FROM consent_records
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()

    scan_rows = [
        {
            "scanned_at": row["scanned_at"],
            "code": row["code"],
            "destination_domain": row["destination_domain"],
            "user_agent": user_agent_summary(row["user_agent"]),
            "referrer": row["referrer"],
            "ip_address": row["ip_address"],
        }
        for row in recent_scans
    ]
    consent_records = [
        {
            "created_at": row["created_at"],
            "consent_status": row["consent_status"],
            "consent_version": row["consent_version"],
            "user_agent": user_agent_summary(row["user_agent"]),
            "ip_address": row["ip_address"],
        }
        for row in consent_rows
    ]

    return render_template_string(
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>DS Digital QR Admin</title>
          <style>
            * { box-sizing: border-box; }
            body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; color: #111827; }
            main { width: min(1280px, 100%); margin: 0 auto; padding: 28px 18px 60px; }
            .header { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 18px; }
            h1 { margin: 0; font-size: clamp(30px, 6vw, 46px); }
            h2 { margin: 30px 0 12px; font-size: 22px; }
            p { color: #64748b; }
            .note { padding: 12px 14px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 12px; color: #9a3412; font-weight: 800; }
            .danger { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
            .logout { display: inline-flex; margin-top: 8px; color: #2563eb; font-weight: 900; }
            .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 18px 0 10px; }
            .metric { padding: 16px; background: white; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05); }
            .metric span { display: block; color: #64748b; font-size: 12px; font-weight: 900; text-transform: uppercase; }
            .metric strong { display: block; margin-top: 6px; font-size: 24px; overflow-wrap: anywhere; }
            .table-wrap { overflow-x: auto; background: white; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06); }
            table { width: 100%; border-collapse: collapse; min-width: 1120px; }
            th, td { padding: 14px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }
            th { color: #344054; font-size: 13px; text-transform: uppercase; letter-spacing: .04em; background: #f8fafc; }
            td { font-size: 14px; }
            a { color: #2563eb; overflow-wrap: anywhere; }
            .code { font-weight: 900; color: #111827; }
            .count { font-weight: 900; }
            .wrap { max-width: 360px; overflow-wrap: anywhere; }
            @media (max-width: 700px) { .header { display: block; } }
          </style>
        </head>
        <body>
          <main>
            <div class="header">
              <div>
                <p>DS Digital Designs</p>
                <h1>DS Digital QR Admin</h1>
                <a class="logout" href="/admin/logout">Log out</a>
              </div>
              <p class="note">Admin password protection is enabled.</p>
            </div>
            <section class="cards" aria-label="Overview">
              <div class="metric"><span>Total QR codes</span><strong>{{ overview.total_qr }}</strong></div>
              <div class="metric"><span>Total scans</span><strong>{{ overview.total_scans }}</strong></div>
              <div class="metric"><span>Scans today</span><strong>{{ overview.scans_today }}</strong></div>
              <div class="metric"><span>QR codes today</span><strong>{{ overview.created_today }}</strong></div>
              <div class="metric"><span>Top design</span><strong>{{ overview.top_design or "" }}</strong></div>
              <div class="metric"><span>Top domain</span><strong>{{ overview.top_domain or "" }}</strong></div>
            </section>
            <h2>QR Links</h2>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Smart URL</th>
                    <th>Destination Domain</th>
                    <th>Title</th>
                    <th>Design</th>
                    <th>Created</th>
                    <th>Scans</th>
                    <th>Last Scanned</th>
                  </tr>
                </thead>
                <tbody>
                  {% for row in qr_rows %}
                  <tr>
                    <td class="code">{{ row.code }}</td>
                    <td><a href="{{ public_base }}/q/{{ row.code }}" target="_blank" rel="noopener">{{ public_base }}/q/{{ row.code }}</a></td>
                    <td class="wrap">{{ row.destination_domain or "" }}</td>
                    <td class="wrap">{{ row.title or "" }}</td>
                    <td>{{ row.design or "" }}</td>
                    <td>{{ row.created_at or "" }}</td>
                    <td class="count">{{ row.scan_count }}</td>
                    <td>{{ row.last_scanned_at or row.scan_last_scanned or "" }}</td>
                  </tr>
                  {% else %}
                  <tr><td colspan="8">No QR records yet.</td></tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
            <h2>Recent Scans</h2>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Scanned At</th><th>Code</th><th>Destination Domain</th><th>User Agent Summary</th><th>Referrer</th><th>IP Address</th></tr></thead>
                <tbody>
                {% for row in scan_rows %}
                  <tr>
                    <td>{{ row.scanned_at }}</td>
                    <td class="code">{{ row.code }}</td>
                    <td class="wrap">{{ row.destination_domain }}</td>
                    <td class="wrap">{{ row.user_agent }}</td>
                    <td class="wrap">{{ row.referrer }}</td>
                    <td>{{ row.ip_address }}</td>
                  </tr>
                {% else %}
                  <tr><td colspan="6">No scans yet.</td></tr>
                {% endfor %}
                </tbody>
              </table>
            </div>
            <h2>Recent Events</h2>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Created At</th><th>Event Type</th><th>Code</th><th>QR Type</th><th>Design</th><th>Consent</th></tr></thead>
                <tbody>
                {% for row in recent_events %}
                  <tr>
                    <td>{{ row.created_at }}</td>
                    <td>{{ row.event_type }}</td>
                    <td class="code">{{ row.code or "" }}</td>
                    <td>{{ row.qr_type or "" }}</td>
                    <td>{{ row.design or "" }}</td>
                    <td>{{ row.consent_status or "" }}</td>
                  </tr>
                {% else %}
                  <tr><td colspan="6">No events yet.</td></tr>
                {% endfor %}
                </tbody>
              </table>
            </div>
            <h2>Consent Records</h2>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Created At</th><th>Status</th><th>Version</th><th>User Agent Summary</th><th>IP Address</th></tr></thead>
                <tbody>
                {% for row in consent_records %}
                  <tr>
                    <td>{{ row.created_at }}</td>
                    <td>{{ row.consent_status }}</td>
                    <td>{{ row.consent_version }}</td>
                    <td class="wrap">{{ row.user_agent }}</td>
                    <td>{{ row.ip_address }}</td>
                  </tr>
                {% else %}
                  <tr><td colspan="5">No consent records yet.</td></tr>
                {% endfor %}
                </tbody>
              </table>
            </div>
          </main>
        </body>
        </html>
        """,
        overview=overview,
        qr_rows=qr_rows,
        scan_rows=scan_rows,
        recent_events=recent_events,
        consent_records=consent_records,
        public_base=PUBLIC_SMART_BASE,
    )


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect("/admin")


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5051, debug=False)
