import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.deps import current_user, get_db, require_admin, require_device
from app.guide import fresh_guide
from app.models import (
    Activity,
    App,
    DeviceToken,
    InstallReport,
    Media,
    Notification,
    PasswordReset,
    User,
    UserApp,
    new_id,
    utcnow,
)
from app.schemas import (
    AppCreate,
    AppUpdate,
    DeviceTokenIn,
    ForgotIn,
    GuideIn,
    InstallReportIn,
    LoginIn,
    OwnPasswords,
    ResetIn,
    UserCreate,
    UserUpdate,
)
from app.security import (
    create_token,
    decrypt_text,
    encrypt_text,
    hash_password,
    hash_token,
    new_reset_token,
    verify_password,
)
from app.services import assigned_user_ids, log_activity, notify, require_apps, user_by_email

router = APIRouter()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _settings(db: Session):
    return db.info["settings"]


def _check_install_method(method: str, play_url: str | None) -> None:
    if method not in {"play", "file"}:
        raise HTTPException(status_code=400, detail="Install method must be play or file")
    if method == "play" and not (play_url or "").startswith("http"):
        raise HTTPException(status_code=400, detail="A Play link is required for Play installs")


def _app_out(app: App) -> dict:
    return {
        "id": app.id,
        "name": app.name,
        "package_name": app.package_name,
        "version": app.version,
        "install_method": app.install_method,
        "play_url": app.play_url,
        "has_file": bool(app.apk_path),
        "apk_filename": app.apk_filename,
        "guide_published": app.guide_published_at is not None,
        "updated_at": app.updated_at,
    }


def _media_url(app_id: str, media_id: str) -> str:
    return f"/apps/{app_id}/media/{media_id}"


def _expand_guide(db: Session, app_id: str, guide: dict | None) -> dict:
    data = guide or fresh_guide()
    media = {item.id: item for item in db.query(Media).filter(Media.app_id == app_id).all()}
    expanded = {}
    for section in ("overview", "setup", "usage", "problems"):
        expanded[section] = []
        for item in data.get(section, []):
            images = []
            videos = []
            for media_id in item.get("image_ids", []):
                row = media.get(media_id)
                if row:
                    images.append({"id": row.id, "name": row.original_name, "url": _media_url(app_id, row.id)})
            for media_id in item.get("video_ids", []):
                row = media.get(media_id)
                if row:
                    videos.append({"id": row.id, "name": row.original_name, "url": _media_url(app_id, row.id)})
            expanded[section].append(
                {
                    "id": item["id"],
                    "title": item["title"],
                    "body": item.get("body", ""),
                    "solution": item.get("solution"),
                    "images": images,
                    "videos": videos,
                }
            )
    return expanded


def _store_guide(db: Session, app: App, payload: GuideIn) -> dict:
    media = {item.id: item for item in db.query(Media).filter(Media.app_id == app.id).all()}
    stored = {}
    for section in ("overview", "setup", "usage", "problems"):
        stored[section] = []
        for item in getattr(payload, section):
            for image_id in item.image_ids:
                row = media.get(image_id)
                if row is None or row.kind != "image":
                    raise HTTPException(status_code=400, detail="Guide image was not found")
            for video_id in item.video_ids:
                row = media.get(video_id)
                if row is None or row.kind != "video":
                    raise HTTPException(status_code=400, detail="Guide video was not found")
            stored[section].append(
                {
                    "id": item.id or new_id(),
                    "title": item.title,
                    "body": item.body,
                    "solution": item.solution,
                    "image_ids": item.image_ids,
                    "video_ids": item.video_ids,
                }
            )
    return stored


def _decrypt(db: Session, value: str | None) -> str | None:
    if not value:
        return None
    return decrypt_text(_settings(db).secret_key, value)


def _apply_app_password(db: Session, user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    user.app_password_encrypted = encrypt_text(_settings(db).secret_key, password)


def _device_profile(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "kind": "device",
        "name": user.name,
        "role": user.role_label,
        "gmail": user.email,
        "gmail_password": _decrypt(db, user.gmail_password_encrypted),
        "app_password": _decrypt(db, user.app_password_encrypted),
    }


def _user_admin_out(db: Session, user: User) -> dict:
    links = db.query(UserApp).filter(UserApp.user_id == user.id).all()
    reports = {
        row.app_id: row
        for row in db.query(InstallReport).filter(InstallReport.user_id == user.id).all()
    }
    apps = []
    for link in links:
        app = db.get(App, link.app_id)
        if app is None:
            continue
        report = reports.get(app.id)
        apps.append(
            {
                "id": app.id,
                "name": app.name,
                "package_name": app.package_name,
                "installed": report.installed if report else False,
                "installed_version": report.installed_version if report else None,
                "reported_at": report.reported_at if report else None,
            }
        )
    notes = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role_label,
        "gmail": user.email,
        "gmail_password": _decrypt(db, user.gmail_password_encrypted),
        "app_password": _decrypt(db, user.app_password_encrypted),
        "apps": apps,
        "notifications": [
            {"id": note.id, "kind": note.kind, "title": note.title, "body": note.body, "created_at": note.created_at}
            for note in notes
        ],
    }


def _assigned(db: Session, user: User, app_id: str) -> App:
    app = db.get(App, app_id)
    link = (
        db.query(UserApp)
        .filter(UserApp.user_id == user.id, UserApp.app_id == app_id)
        .one_or_none()
    )
    if app is None or link is None:
        raise HTTPException(status_code=404, detail="App not found")
    return app


def _save_upload(db: Session, folder: str, upload: UploadFile) -> Path:
    settings = _settings(db)
    target_dir = settings.storage_path() / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "file").suffix
    path = target_dir / f"{new_id()}{suffix}"
    path.write_bytes(upload.file.read())
    return path


def _remove_file(path: str | None) -> None:
    if not path:
        return
    file = Path(path)
    if file.is_file():
        file.unlink()


def _delete_user_rows(db: Session, user_id: str) -> None:
    db.query(UserApp).filter(UserApp.user_id == user_id).delete(synchronize_session=False)
    db.query(InstallReport).filter(InstallReport.user_id == user_id).delete(synchronize_session=False)
    db.query(DeviceToken).filter(DeviceToken.user_id == user_id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)
    db.query(PasswordReset).filter(PasswordReset.user_id == user_id).delete(synchronize_session=False)


def _delete_app_rows(db: Session, app: App) -> None:
    media = db.query(Media).filter(Media.app_id == app.id).all()
    paths = [app.apk_path, *[item.path for item in media]]
    db.query(UserApp).filter(UserApp.app_id == app.id).delete(synchronize_session=False)
    db.query(InstallReport).filter(InstallReport.app_id == app.id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.app_id == app.id).delete(synchronize_session=False)
    db.query(Media).filter(Media.app_id == app.id).delete(synchronize_session=False)
    for path in paths:
        _remove_file(path)


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = user_by_email(db, str(body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    settings = _settings(db)
    return {
        "access_token": create_token(settings, user.id, user.kind),
        "token_type": "bearer",
        "kind": user.kind,
    }


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    user = user_by_email(db, str(body.email))
    token = None
    if user is not None:
        raw = new_reset_token()
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        db.commit()
        if _settings(db).expose_reset_token:
            token = raw
    response = {"ok": True}
    if token:
        response["reset_token"] = token
    return response


@router.post("/auth/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    row = (
        db.query(PasswordReset)
        .filter(PasswordReset.token_hash == hash_token(body.token), PasswordReset.used.is_(False))
        .one_or_none()
    )
    if row is None or _aware(row.expires_at) < utcnow():
        raise HTTPException(status_code=400, detail="Reset link is invalid")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Reset link is invalid")
    _apply_app_password(db, user, body.password)
    row.used = True
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.kind == "admin":
        return {"id": user.id, "kind": "admin", "name": user.name, "email": user.email}
    return _device_profile(db, user)


@router.patch("/me/passwords")
def update_own_passwords(body: OwnPasswords, user: User = Depends(require_device), db: Session = Depends(get_db)):
    if body.gmail_password is None and body.app_password is None:
        raise HTTPException(status_code=400, detail="Enter a password to change")
    if body.gmail_password is not None:
        user.gmail_password_encrypted = encrypt_text(_settings(db).secret_key, body.gmail_password)
    if body.app_password is not None:
        _apply_app_password(db, user, body.app_password)
    db.commit()
    db.refresh(user)
    return _device_profile(db, user)


@router.get("/admin/summary")
def summary(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    activities = db.query(Activity).order_by(Activity.created_at.desc()).limit(20).all()
    return {
        "users": db.query(User).filter(User.kind == "device").count(),
        "apps": db.query(App).count(),
        "activities": [
            {"id": row.id, "kind": row.kind, "message": row.message, "created_at": row.created_at}
            for row in activities
        ],
    }


@router.get("/admin/users")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.kind == "device").order_by(User.created_at.desc()).all()
    return [_user_admin_out(db, user) for user in users]


@router.post("/admin/users", status_code=201)
def create_user(body: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = str(body.gmail).lower()
    if user_by_email(db, email):
        raise HTTPException(status_code=409, detail="This email is already registered")
    require_apps(db, body.app_ids)
    user = User(
        kind="device",
        name=body.name,
        email=email,
        password_hash=hash_password(body.app_password),
        role_label=body.role,
        gmail_password_encrypted=encrypt_text(_settings(db).secret_key, body.gmail_password),
        app_password_encrypted=encrypt_text(_settings(db).secret_key, body.app_password),
    )
    db.add(user)
    db.flush()
    for app_id in body.app_ids:
        db.add(UserApp(user_id=user.id, app_id=app_id))
    log_activity(db, "user_created", f"User {user.name} was created")
    if body.app_ids:
        notify(db, [user.id], "apps", "App list", "Your apps have been assigned")
    db.commit()
    db.refresh(user)
    return _user_admin_out(db, user)


@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.kind != "device":
        raise HTTPException(status_code=404, detail="User not found")
    if body.name is not None:
        user.name = body.name
    if body.role is not None:
        user.role_label = body.role
    if body.gmail is not None:
        email = str(body.gmail).lower()
        existing = user_by_email(db, email)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=409, detail="This email is already registered")
        user.email = email
    if body.gmail_password is not None:
        user.gmail_password_encrypted = encrypt_text(_settings(db).secret_key, body.gmail_password)
    if body.app_password is not None:
        _apply_app_password(db, user, body.app_password)
    if body.app_ids is not None:
        require_apps(db, body.app_ids)
        previous = {row.app_id for row in db.query(UserApp).filter(UserApp.user_id == user.id).all()}
        db.query(UserApp).filter(UserApp.user_id == user.id).delete()
        db.flush()
        for app_id in body.app_ids:
            db.add(UserApp(user_id=user.id, app_id=app_id))
        if previous != set(body.app_ids):
            notify(db, [user.id], "apps", "App list", "Your apps have changed")
    log_activity(db, "user_updated", f"User {user.name} was updated")
    db.commit()
    db.refresh(user)
    return _user_admin_out(db, user)


@router.delete("/admin/users/{user_id}", status_code=204)
def delete_user(user_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.kind != "device":
        raise HTTPException(status_code=404, detail="User not found")
    name = user.name
    _delete_user_rows(db, user.id)
    db.delete(user)
    log_activity(db, "user_deleted", f"User {name} was deleted")
    db.commit()


@router.get("/admin/apps")
def list_apps(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    apps = db.query(App).order_by(App.created_at.desc()).all()
    return [_app_out(app) for app in apps]


@router.post("/admin/apps", status_code=201)
def create_app(body: AppCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    _check_install_method(body.install_method, body.play_url)
    if db.query(App).filter(App.package_name == body.package_name).one_or_none():
        raise HTTPException(status_code=409, detail="This package name is already registered")
    app = App(
        name=body.name,
        package_name=body.package_name,
        version=body.version,
        install_method=body.install_method,
        play_url=body.play_url if body.install_method == "play" else None,
        guide_draft=fresh_guide(),
    )
    db.add(app)
    log_activity(db, "app_created", f"App {app.name} was created")
    db.commit()
    db.refresh(app)
    return _app_out(app)


@router.patch("/admin/apps/{app_id}")
def update_app(app_id: str, body: AppUpdate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    version_changed = body.version is not None and body.version != app.version
    if body.name is not None:
        app.name = body.name
    if body.package_name is not None:
        existing = db.query(App).filter(App.package_name == body.package_name).one_or_none()
        if existing and existing.id != app.id:
            raise HTTPException(status_code=409, detail="This package name is already registered")
        app.package_name = body.package_name
    if body.version is not None:
        app.version = body.version
    if body.install_method is not None:
        play_url = body.play_url if body.play_url is not None else app.play_url
        _check_install_method(body.install_method, play_url)
        app.install_method = body.install_method
        if body.install_method == "file":
            app.play_url = None
    if body.play_url is not None and app.install_method == "play":
        _check_install_method("play", body.play_url)
        app.play_url = body.play_url
    app.updated_at = utcnow()
    log_activity(db, "app_updated", f"App {app.name} was updated")
    if version_changed:
        notify(
            db,
            assigned_user_ids(db, app.id),
            "apk",
            "New version",
            f"{app.name} is now version {app.version}",
            app.id,
        )
    db.commit()
    db.refresh(app)
    return _app_out(app)


@router.delete("/admin/apps/{app_id}", status_code=204)
def delete_app(app_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    name = app.name
    _delete_app_rows(db, app)
    db.delete(app)
    log_activity(db, "app_deleted", f"App {name} was deleted")
    db.commit()


@router.post("/admin/apps/{app_id}/file")
def upload_apk(
    app_id: str,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    if app.install_method != "file":
        raise HTTPException(status_code=400, detail="This app is not installed from a server file")
    if not (file.filename or "").lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="File must be an APK")
    path = _save_upload(db, "apk", file)
    app.apk_path = str(path)
    app.apk_filename = file.filename
    app.updated_at = utcnow()
    log_activity(db, "apk_replaced", f"Install file for {app.name} was replaced")
    notify(
        db,
        assigned_user_ids(db, app.id),
        "apk",
        "New install file",
        f"The install file for {app.name} was updated",
        app.id,
    )
    db.commit()
    return _app_out(app)


@router.get("/admin/apps/{app_id}/guide")
def admin_guide(app_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return {
        "draft": _expand_guide(db, app.id, app.guide_draft),
        "published": _expand_guide(db, app.id, app.guide_published) if app.guide_published else None,
    }


@router.put("/admin/apps/{app_id}/guide")
def save_guide(app_id: str, body: GuideIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    app.guide_draft = _store_guide(db, app, body)
    flag_modified(app, "guide_draft")
    app.updated_at = utcnow()
    db.commit()
    return {"draft": _expand_guide(db, app.id, app.guide_draft)}


@router.post("/admin/apps/{app_id}/media", status_code=201)
def upload_media(
    app_id: str,
    kind: str,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    if kind not in {"image", "video"}:
        raise HTTPException(status_code=400, detail="File kind must be image or video")
    path = _save_upload(db, kind, file)
    media = Media(app_id=app.id, kind=kind, path=str(path), original_name=file.filename or kind)
    db.add(media)
    db.commit()
    db.refresh(media)
    return {"id": media.id, "kind": media.kind, "name": media.original_name, "url": _media_url(app.id, media.id)}


@router.post("/admin/apps/{app_id}/guide/publish")
def publish_guide(app_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    app.guide_published = app.guide_draft or fresh_guide()
    flag_modified(app, "guide_published")
    app.guide_published_at = utcnow()
    log_activity(db, "guide_published", f"Guide for {app.name} was published")
    notify(
        db,
        assigned_user_ids(db, app.id),
        "guide",
        "New guide",
        f"The guide for {app.name} was published",
        app.id,
    )
    db.commit()
    return {"published": _expand_guide(db, app.id, app.guide_published)}


@router.get("/apps")
def device_apps(user: User = Depends(require_device), db: Session = Depends(get_db)):
    links = db.query(UserApp).filter(UserApp.user_id == user.id).all()
    result = []
    for link in links:
        app = db.get(App, link.app_id)
        if app is None:
            continue
        result.append(
            {
                "id": app.id,
                "name": app.name,
                "package_name": app.package_name,
                "version": app.version,
                "install_method": app.install_method,
                "play_url": app.play_url if app.install_method == "play" else None,
                "has_file": bool(app.apk_path) and app.install_method == "file",
                "guide_published": app.guide_published is not None,
            }
        )
    return result


@router.get("/apps/{app_id}/guide")
def device_guide(app_id: str, user: User = Depends(require_device), db: Session = Depends(get_db)):
    app = _assigned(db, user, app_id)
    if not app.guide_published:
        raise HTTPException(status_code=404, detail="Guide is not published yet")
    return _expand_guide(db, app.id, app.guide_published)


@router.get("/apps/{app_id}/file")
def device_file(app_id: str, user: User = Depends(require_device), db: Session = Depends(get_db)):
    app = _assigned(db, user, app_id)
    if app.install_method != "file" or not app.apk_path:
        raise HTTPException(status_code=404, detail="Install file is not available")
    return FileResponse(app.apk_path, filename=app.apk_filename or "app.apk", media_type="application/vnd.android.package-archive")


@router.get("/apps/{app_id}/media/{media_id}")
def read_media(app_id: str, media_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    media = db.get(Media, media_id)
    if media is None or media.app_id != app_id:
        raise HTTPException(status_code=404, detail="File not found")
    if user.kind == "device":
        app = _assigned(db, user, app_id)
        published = app.guide_published or {}
        allowed: set[str] = set()
        for section in ("overview", "setup", "usage", "problems"):
            for item in published.get(section, []):
                allowed.update(item.get("image_ids", []))
                allowed.update(item.get("video_ids", []))
        if media_id not in allowed:
            raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(media.path, filename=media.original_name)


@router.post("/device/status")
def device_status(body: InstallReportIn, user: User = Depends(require_device), db: Session = Depends(get_db)):
    assigned = {row.app_id for row in db.query(UserApp).filter(UserApp.user_id == user.id).all()}
    unknown = [item.app_id for item in body.items if item.app_id not in assigned]
    if unknown:
        raise HTTPException(status_code=400, detail="This app is not assigned to you")
    for item in body.items:
        row = (
            db.query(InstallReport)
            .filter(InstallReport.user_id == user.id, InstallReport.app_id == item.app_id)
            .one_or_none()
        )
        if row is None:
            row = InstallReport(user_id=user.id, app_id=item.app_id, installed=item.installed)
            db.add(row)
        row.installed = item.installed
        row.installed_version = item.version
        row.reported_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/device/token")
def device_token(body: DeviceTokenIn, user: User = Depends(require_device), db: Session = Depends(get_db)):
    existing = db.query(DeviceToken).filter(DeviceToken.token == body.token).one_or_none()
    if existing is None:
        db.add(DeviceToken(user_id=user.id, token=body.token, platform=body.platform))
    else:
        existing.user_id = user.id
        existing.platform = body.platform
    db.commit()
    return {"ok": True}