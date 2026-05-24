import secrets
import sqlite3
import string
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, jsonify, redirect, render_template_string, request
from flask_cors import CORS


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "ds_smart_qr.db"
SMART_URL_BASE = "https://dsdigitaldesigns.org/qr/redirect.html"
ALPHABET = string.ascii_letters + string.digits

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://dsdigitaldesigns.org",
                "http://127.0.0.1:5050",
                "http://localhost:5050",
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
        smart_url=f"{SMART_URL_BASE}?c={code}",
        destination_url=destination_url,
    )


@app.get("/api/resolve/<code>")
def resolve_qr(code):
    clean_code = clean_text(code, 12)
    db = get_db()
    row = db.execute("SELECT * FROM qr_links WHERE code = ?", (clean_code,)).fetchone()

    if row is None:
        return jsonify(ok=False, error="QR code not found."), 404

    db.execute(
        "UPDATE qr_links SET scan_count = scan_count + 1 WHERE code = ?",
        (clean_code,),
    )
    db.execute(
        """
        INSERT INTO qr_scans (code, scanned_at, user_agent, referrer, ip_address)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            clean_code,
            utc_now(),
            request.headers.get("User-Agent", ""),
            request.headers.get("Referer", ""),
            request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        ),
    )
    db.commit()

    return jsonify(
        ok=True,
        destination_url=row["destination_url"],
        title=row["title"] or "",
        code=row["code"],
    )


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
    app.run(host="127.0.0.1", port=5050, debug=True)
