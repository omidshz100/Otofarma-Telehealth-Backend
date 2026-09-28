from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        storage_dir=str(tmp_path / "storage"),
        secret_key="test-secret",
        admin_email="admin@example.com",
        admin_password="admin-pass-123",
        admin_name="Admin",
        expose_reset_token=True,
    )
    return TestClient(create_app(settings))


def _auth(client, email, password):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_full_flow(tmp_path):
    client = _client(tmp_path)
    admin = _auth(client, "admin@example.com", "admin-pass-123")

    me = client.get("/me", headers=admin)
    assert me.status_code == 200
    assert me.json()["kind"] == "admin"
    assert "gmail_password" not in me.json()

    play = client.post(
        "/admin/apps",
        headers=admin,
        json={
            "name": "ECG",
            "package_name": "com.otofarma.ecg",
            "version": "1.0.0",
            "install_method": "play",
            "play_url": "https://play.google.com/store/apps/details?id=com.otofarma.ecg",
        },
    )
    assert play.status_code == 201, play.text
    play_id = play.json()["id"]

    local = client.post(
        "/admin/apps",
        headers=admin,
        json={
            "name": "SpO2",
            "package_name": "com.otofarma.spo2",
            "version": "1.0.0",
            "install_method": "file",
        },
    )
    assert local.status_code == 201, local.text
    local_id = local.json()["id"]

    apk = client.post(
        f"/admin/apps/{local_id}/file",
        headers=admin,
        files={"file": ("spo2.apk", b"apk-bytes", "application/vnd.android.package-archive")},
    )
    assert apk.status_code == 200, apk.text
    assert apk.json()["has_file"] is True

    image = client.post(
        f"/admin/apps/{local_id}/media?kind=image",
        headers=admin,
        files={"file": ("step.png", b"png", "image/png")},
    )
    assert image.status_code == 201, image.text
    image_id = image.json()["id"]

    saved = client.put(
        f"/admin/apps/{local_id}/guide",
        headers=admin,
        json={
            "setup": [
                {
                    "title": "Connect the cable",
                    "body": "Attach the adapter before turning the device on",
                    "image_ids": [image_id],
                }
            ],
            "usage": [{"title": "Take a reading", "body": "Press start"}],
            "problems": [{"title": "No signal", "body": "The cable is loose", "solution": "Reconnect the cable"}],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft"]["setup"][0]["images"][0]["id"] == image_id

    created = client.post(
        "/admin/users",
        headers=admin,
        json={
            "name": "Giulia",
            "role": "Pharmacy",
            "gmail": "giulia@gmail.com",
            "gmail_password": "gmail-pass-123",
            "app_password": "app-pass-123",
            "app_ids": [local_id],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["gmail_password"] == "gmail-pass-123"
    assert created.json()["app_password"] == "app-pass-123"
    user_id = created.json()["id"]

    device = _auth(client, "giulia@gmail.com", "app-pass-123")
    assert client.get("/admin/users", headers=device).status_code == 403
    profile = client.get("/me", headers=device)
    assert profile.status_code == 200
    assert profile.json()["gmail"] == "giulia@gmail.com"
    assert profile.json()["gmail_password"] == "gmail-pass-123"
    assert profile.json()["app_password"] == "app-pass-123"
    assert "app_password" not in me.json()

    hidden = client.get(f"/apps/{local_id}/guide", headers=device)
    assert hidden.status_code == 404

    published = client.post(f"/admin/apps/{local_id}/guide/publish", headers=admin)
    assert published.status_code == 200, published.text

    apps = client.get("/apps", headers=device)
    assert apps.status_code == 200
    assert [item["package_name"] for item in apps.json()] == ["com.otofarma.spo2"]

    guide = client.get(f"/apps/{local_id}/guide", headers=device)
    assert guide.status_code == 200
    assert guide.json()["problems"][0]["solution"] == "Reconnect the cable"
    media_url = guide.json()["setup"][0]["images"][0]["url"]
    assert client.get(media_url, headers=device).status_code == 200

    downloaded = client.get(f"/apps/{local_id}/file", headers=device)
    assert downloaded.status_code == 200
    assert downloaded.content == b"apk-bytes"
    assert client.get(f"/apps/{play_id}/file", headers=device).status_code == 404

    status = client.post(
        "/device/status",
        headers=device,
        json={"items": [{"app_id": local_id, "installed": True, "version": "1.0.0"}]},
    )
    assert status.status_code == 200
    token = client.post("/device/token", headers=device, json={"token": "device-token-123", "platform": "android"})
    assert token.status_code == 200

    users = client.get("/admin/users", headers=admin)
    giulia = next(item for item in users.json() if item["id"] == user_id)
    assert giulia["apps"][0]["installed"] is True
    assert giulia["apps"][0]["installed_version"] == "1.0.0"
    assert any(note["kind"] == "guide" for note in giulia["notifications"])

    edited = client.put(
        f"/admin/apps/{local_id}/guide",
        headers=admin,
        json={"setup": [{"title": "Updated sentence", "body": "Only the text changed"}], "usage": [], "problems": []},
    )
    assert edited.status_code == 200
    still = client.get(f"/apps/{local_id}/guide", headers=device)
    assert still.json()["setup"][0]["title"] == "Connect the cable"

    replaced = client.post(
        f"/admin/apps/{local_id}/file",
        headers=admin,
        files={"file": ("spo2-2.apk", b"apk-v2", "application/vnd.android.package-archive")},
    )
    assert replaced.status_code == 200
    users = client.get("/admin/users", headers=admin).json()
    giulia = next(item for item in users if item["id"] == user_id)
    assert any(note["kind"] == "apk" for note in giulia["notifications"])

    changed = client.patch(
        "/me/passwords",
        headers=device,
        json={"gmail_password": "gmail-new-123", "app_password": "app-new-1234"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["gmail_password"] == "gmail-new-123"
    assert changed.json()["app_password"] == "app-new-1234"
    assert client.post("/auth/login", json={"email": "giulia@gmail.com", "password": "app-pass-123"}).status_code == 401
    _auth(client, "giulia@gmail.com", "app-new-1234")
    assert client.patch("/me/passwords", headers=admin, json={"app_password": "admin-no-change"}).status_code == 403
    seen = next(item for item in client.get("/admin/users", headers=admin).json() if item["id"] == user_id)
    assert seen["gmail_password"] == "gmail-new-123"
    assert seen["app_password"] == "app-new-1234"

    forgot = client.post("/auth/forgot-password", json={"email": "giulia@gmail.com"})
    assert forgot.status_code == 200
    reset = client.post(
        "/auth/reset-password",
        json={"token": forgot.json()["reset_token"], "password": "new-app-pass"},
    )
    assert reset.status_code == 200
    _auth(client, "giulia@gmail.com", "new-app-pass")
    reset_seen = next(item for item in client.get("/admin/users", headers=admin).json() if item["id"] == user_id)
    assert reset_seen["app_password"] == "new-app-pass"

    summary = client.get("/admin/summary", headers=admin)
    assert summary.status_code == 200
    assert summary.json()["users"] == 1
    assert summary.json()["apps"] == 2
    assert summary.json()["activities"]


def test_delete_user_and_app(tmp_path):
    client = _client(tmp_path)
    admin = _auth(client, "admin@example.com", "admin-pass-123")
    admin_id = client.get("/me", headers=admin).json()["id"]

    kept = client.post(
        "/admin/apps",
        headers=admin,
        json={
            "name": "ECG",
            "package_name": "com.otofarma.ecg",
            "version": "1.0.0",
            "install_method": "play",
            "play_url": "https://play.google.com/store/apps/details?id=com.otofarma.ecg",
        },
    )
    assert kept.status_code == 201, kept.text
    kept_id = kept.json()["id"]

    removed = client.post(
        "/admin/apps",
        headers=admin,
        json={"name": "SpO2", "package_name": "com.otofarma.spo2", "version": "1.0.0", "install_method": "file"},
    )
    assert removed.status_code == 201, removed.text
    removed_id = removed.json()["id"]
    uploaded = client.post(
        f"/admin/apps/{removed_id}/file",
        headers=admin,
        files={"file": ("spo2.apk", b"apk-bytes", "application/vnd.android.package-archive")},
    )
    assert uploaded.status_code == 200, uploaded.text
    image = client.post(
        f"/admin/apps/{removed_id}/media?kind=image",
        headers=admin,
        files={"file": ("step.png", b"png", "image/png")},
    )
    assert image.status_code == 201, image.text
    stored = list((tmp_path / "storage").rglob("*"))
    assert any(path.is_file() for path in stored)

    created = client.post(
        "/admin/users",
        headers=admin,
        json={
            "name": "Giulia",
            "role": "Pharmacy",
            "gmail": "giulia@gmail.com",
            "gmail_password": "gmail-pass-123",
            "app_password": "app-pass-123",
            "app_ids": [kept_id, removed_id],
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    device = _auth(client, "giulia@gmail.com", "app-pass-123")
    assert client.post(
        "/device/status",
        headers=device,
        json={"items": [{"app_id": removed_id, "installed": True, "version": "1.0.0"}]},
    ).status_code == 200
    assert client.post("/device/token", headers=device, json={"token": "device-token-123"}).status_code == 200
    assert client.post("/auth/forgot-password", json={"email": "giulia@gmail.com"}).status_code == 200

    assert client.delete(f"/admin/apps/{removed_id}", headers=device).status_code == 403
    deleted_app = client.delete(f"/admin/apps/{removed_id}", headers=admin)
    assert deleted_app.status_code == 204, deleted_app.text
    assert client.get(f"/admin/apps/{removed_id}/guide", headers=admin).status_code == 404
    assert client.delete(f"/admin/apps/{removed_id}", headers=admin).status_code == 404
    listed = client.get("/admin/users", headers=admin).json()
    giulia = next(item for item in listed if item["id"] == user_id)
    assert [item["id"] for item in giulia["apps"]] == [kept_id]
    device_apps = client.get("/apps", headers=device).json()
    assert [item["id"] for item in device_apps] == [kept_id]
    assert not any(path.is_file() for path in (tmp_path / "storage").rglob("*"))

    assert client.delete(f"/admin/users/{admin_id}", headers=admin).status_code == 404
    assert client.delete(f"/admin/users/{user_id}", headers=device).status_code == 403
    deleted_user = client.delete(f"/admin/users/{user_id}", headers=admin)
    assert deleted_user.status_code == 204, deleted_user.text
    assert client.get("/admin/users", headers=admin).json() == []
    assert client.post("/auth/login", json={"email": "giulia@gmail.com", "password": "app-pass-123"}).status_code == 401
    assert client.delete(f"/admin/users/{user_id}", headers=admin).status_code == 404
    summary = client.get("/admin/summary", headers=admin).json()
    assert summary["users"] == 0
    assert summary["apps"] == 1
