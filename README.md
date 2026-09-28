# Otofarma backend

API for the dashboard and the device app. Gmail mailboxes are not created here. An admin stores the Gmail address and password.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

The first admin login is read from `.env`. Default: `admin@example.com` / `admin12345`

## Test

```bash
pytest
```

Notifications are stored in the database and shown on the admin user list. Delivery to the phone notification tray comes after Firebase is configured.
