from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.models import User
from app.security import read_token

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request):
    db: Session = request.app.state.session_factory()
    db.info["settings"] = request.app.state.settings
    try:
        yield db
    finally:
        db.close()


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    settings = db.info["settings"]
    try:
        payload = read_token(settings, credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.kind != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can use the dashboard")
    return user


def require_device(user: User = Depends(current_user)) -> User:
    if user.kind != "device":
        raise HTTPException(status_code=403, detail="This route is only for the device app")
    return user
