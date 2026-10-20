# Otofarma Telehealth Backend

API for the Otofarma admin dashboard and the Android companion. The two clients do not talk to each other. Both use this service.

The API does not create Gmail mailboxes. An administrator creates each mailbox outside the platform, then stores the address and password here.

- Android: https://github.com/omidshz100/Otofarma-Telehealth-Android
- Dashboard: https://github.com/omidshz100/Otofarma-Telehealth-Dashboard

## Requirements

- Python 3.10 or newer

## Run

Open a terminal in this backend folder. The folder must contain `app/main.py` and `requirements.txt`.

First time only:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Every time you start the API:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Leave that terminal open. Stop the server with Ctrl+C.

When it is running, open http://127.0.0.1:8000/docs on this computer. A page titled Otofarma API means the server is up.

`--host 0.0.0.0` accepts connections from a phone or tablet on the same network. `--reload` restarts the server when Python files change.

The dashboard calls this API through http://127.0.0.1:8000. The Android app calls the computer's LAN address, which is `BASE_URL` in the Android project. On macOS, print that address with:

```bash
ipconfig getifaddr en0
```

The phone address is `http://<that-ip>:8000`. If the IP changes, update `BASE_URL` and run the Android app again.

The first start creates the administrator from `.env` when that email is not already in the database. Default login: `admin@example.com` / `admin12345`.

Check the tests while the virtualenv is active:

```bash
pytest
```

## Configuration

Copy `.env.example` to `.env`. The real `.env` is not committed.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL. Default is SQLite at `sqlite:///./data/app.db`. A Postgres URL can replace it later. |
| `SECRET_KEY` | Signs JWT sessions and encrypts stored passwords. |
| `ADMIN_EMAIL` | Email of the single seeded administrator. |
| `ADMIN_PASSWORD` | Password of that administrator. Used only when the account is first created. |
| `ADMIN_NAME` | Display name of that administrator. |
| `STORAGE_DIR` | Directory for uploaded APK, image, and video files. Default `./storage`. |
| `EXPOSE_RESET_TOKEN` | When true, forgot-password returns the reset token in the JSON response. Leave this off outside local development. |

Sessions last 14 days. CORS allows every origin so the dashboard and devices can call the API during development.

## Accounts

There is one administrator. Device users cannot call `/admin` routes. The administrator cannot call device-only routes.

A device user has a name, a role label, a Gmail address, a Gmail password, an app password, and a list of assigned applications. The role label is stored and shown in the app. It does not decide which apps the person sees. The Gmail address is also the sign-in email.

Two passwords are stored for each device user:

- **Gmail password.** Encrypted so the admin and the device can read it. Changing it updates the stored copy only. It does not change the Google account.
- **App password.** This is the Otofarma sign-in password. It is hashed for login and also encrypted so the admin and the signed-in user can read it. Minimum length is 8 characters.

`GET /me` returns both passwords for a device user. For the administrator it returns only id, kind, name, and email.

`PATCH /me/passwords` lets the signed-in device user change either password. The administrator changes them with `PATCH /admin/users/{id}`.

## Applications

Each application has a name, Android package name, version, and one install source:

- `play`, with an `http` Play Store URL
- `file`, with an APK uploaded to `POST /admin/apps/{id}/file` after the application exists

The device list, `GET /apps`, returns only the apps assigned to that user, including the install source. The device compares package names locally and reports installed or not, plus the installed version, to `POST /device/status`.

## Guides

A guide has four sections: overview, setup, usage, and problems. Each block can have a title, body, solution, images, and videos.

`PUT /admin/apps/{id}/guide` saves a draft. The device cannot read a draft. `POST /admin/apps/{id}/guide/publish` copies the draft to the published guide. Publishing does not require a new APK, and editing text does not replace the APK.

## Notifications

Creating a user, changing assigned apps, publishing a guide, or replacing an APK stores a notification for the affected user. The dashboard shows the latest notices on the user page. Delivery to the phone notification tray is not implemented. That needs Firebase later.

`POST /device/token` stores a device token for that later step.

## Tests

```bash
pytest
```

The suite covers admin and device sign-in, applications, guides, file upload, install reports, password changes, and deletion.

`bruno/` is a Bruno collection for the same API. Its local environment points at `http://127.0.0.1:8000` and uses the default admin password. Bruno reads the global environment, not only the collection environment.

## What is not in this version

- Creating Gmail mailboxes
- More than one administrator
- Silent remote install, update, or uninstall
- Phone notification tray
- Postgres as the running database. SQLite is the default.
