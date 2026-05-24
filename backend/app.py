import secrets
import sqlite3
import string
from datetime import datetime, timezone
from os import environ
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, jsonify, redirect, render_template_string, request
from flask_cors import CORS


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "ds_smart_qr.db"
PUBLIC_SMART_BASE = environ.get("PUBLIC_SMART_BASE", "https://kali.tail768496.ts.net").rstrip("/")
ALPHABET = string.ascii_letters + string.digits

app = Flask(__name__)
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
        """
    )
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


def clean_text(value, max_length):
    if value is None:
        return ""
    return str(value).strip()[:max_length]


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


def record_scan(db, code):
    db.execute(
        "UPDATE qr_links SET scan_count = scan_count + 1 WHERE code = ?",
        (code,),
    )
    db.execute(
        """
        INSERT INTO qr_scans (code, scanned_at, user_agent, referrer, ip_address)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            code,
            utc_now(),
            request.headers.get("User-Agent", ""),
            request.headers.get("Referer", ""),
            request_ip(),
        ),
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
    design = clean_text(data.get("design"), 30)
    qr_color = clean_text(data.get("qr_color"), 20)
    bg_color = clean_text(data.get("bg_color"), 20)
    size = clean_text(data.get("size"), 12)

    db = get_db()
    db.execute(
        """
        INSERT INTO qr_links
            (code, destination_url, title, design, qr_color, bg_color, size, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (code, destination_url, title, design, qr_color, bg_color, size, utc_now()),
    )
    db.commit()

    return jsonify(
        ok=True,
        code=code,
        smart_url=f"{PUBLIC_SMART_BASE}/q/{code}",
        destination_url=destination_url,
    )


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
      animation: fill 2.1s ease-out forwards;
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
        }, 2100);
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


@app.get("/admin")
def admin():
    # TODO: Add password protection before any public release.
    rows = get_db().execute(
        """
        SELECT code, destination_url, title, created_at, scan_count
        FROM qr_links
        ORDER BY id DESC
        LIMIT 200
        """
    ).fetchall()

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
            main { width: min(1120px, 100%); margin: 0 auto; padding: 28px 18px 60px; }
            .header { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 18px; }
            h1 { margin: 0; font-size: clamp(30px, 6vw, 46px); }
            p { color: #64748b; }
            .note { padding: 12px 14px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 12px; color: #9a3412; font-weight: 700; }
            .table-wrap { overflow-x: auto; background: white; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06); }
            table { width: 100%; border-collapse: collapse; min-width: 780px; }
            th, td { padding: 14px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }
            th { color: #344054; font-size: 13px; text-transform: uppercase; letter-spacing: .04em; background: #f8fafc; }
            td { font-size: 14px; }
            a { color: #2563eb; overflow-wrap: anywhere; }
            .code { font-weight: 900; color: #111827; }
            .count { font-weight: 900; }
            @media (max-width: 700px) { .header { display: block; } }
          </style>
        </head>
        <body>
          <main>
            <div class="header">
              <div>
                <p>DS Digital Designs</p>
                <h1>DS Digital QR Admin</h1>
              </div>
              <p class="note">Local testing only. Add authentication before public release.</p>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Destination URL</th>
                    <th>Title</th>
                    <th>Created</th>
                    <th>Scans</th>
                  </tr>
                </thead>
                <tbody>
                  {% for row in rows %}
                  <tr>
                    <td class="code">{{ row.code }}</td>
                    <td><a href="{{ row.destination_url }}" target="_blank" rel="noopener">{{ row.destination_url }}</a></td>
                    <td>{{ row.title or "" }}</td>
                    <td>{{ row.created_at or "" }}</td>
                    <td class="count">{{ row.scan_count }}</td>
                  </tr>
                  {% else %}
                  <tr><td colspan="5">No QR records yet.</td></tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          </main>
        </body>
        </html>
        """,
        rows=rows,
    )


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5051, debug=False)
