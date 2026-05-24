# DS Digital QR Backend

Local Flask backend for DS Digital QR smart redirect records.

## Run locally

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

The API runs on:

```text
http://127.0.0.1:5051
```

The SQLite database is created automatically at:

```text
backend/ds_smart_qr.db
```

## Endpoints

- `POST /api/create` creates a smart QR record.
- `GET /q/<code>` records a scan, shows the DS Digital QR intro, and redirects server-side.
- `GET /api/resolve/<code>` records a scan and returns the destination URL.
- `GET /admin` shows a local testing dashboard.

Before public release, put the backend behind HTTPS and password-protect `/admin`.
