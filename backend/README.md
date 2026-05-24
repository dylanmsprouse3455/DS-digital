# DS Digital QR Backend

Local Flask backend for DS Digital QR smart redirect records.

## Run locally

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD="local-admin-password"
export SECRET_KEY="local-dev-secret-key"
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
- `GET /admin` shows the protected admin dashboard.
- `GET /admin/logout` logs out of the admin dashboard.

## Admin protection

The admin dashboard requires these environment variables in production:

```bash
ADMIN_PASSWORD="CHANGE_ME"
SECRET_KEY="CHANGE_ME_LONG_RANDOM_STRING"
```

Do not hard-code either value in `app.py`. `SECRET_KEY` signs Flask admin sessions. If it is missing, the app generates a temporary development key, which is only suitable for local testing.

If `ADMIN_PASSWORD` is not set, `/admin` will not show dashboard data. It will show a warning page explaining that the password must be configured.

## systemd environment

For the `ds-digital-qr.service` unit, add environment lines like this under `[Service]`:

```ini
Environment="ADMIN_PASSWORD=CHANGE_ME"
Environment="SECRET_KEY=CHANGE_ME_LONG_RANDOM_STRING"
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ds-digital-qr
```
