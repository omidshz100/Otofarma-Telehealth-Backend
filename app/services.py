from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Activity, App, Notification, User, UserApp, utcnow


def log_activity(db: Session, kind: str, message: str) -> None:
    db.add(Activity(kind=kind, message=message))


def assigned_user_ids(db: Session, app_id: str) -> list[str]:
    rows = db.query(UserApp.user_id).filter(UserApp.app_id == app_id).all()
    return [row[0] for row in rows]


def notify(db: Session, user_ids: list[str], kind: str, title: str, body: str, app_id: str | None = None) -> None:
    seen: set[str] = set()
    for user_id in user_ids:
        if user_id in seen:
            continue
        seen.add(user_id)
        db.add(
            Notification(
                user_id=user_id,
                app_id=app_id,
                kind=kind,
                title=title,
                body=body,
                created_at=utcnow(),
            )
        )


def require_apps(db: Session, app_ids: list[str]) -> list[App]:
    if not app_ids:
        return []
    apps = db.query(App).filter(App.id.in_(app_ids)).all()
    found = {app.id for app in apps}
    missing = [app_id for app_id in app_ids if app_id not in found]
    if missing:
        raise HTTPException(status_code=400, detail="One of the apps was not found")
    return apps


def user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower()).one_or_none()
