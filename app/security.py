import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.config import Settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_text(secret: str, value: str) -> str:
    return _fernet(secret).encrypt(value.encode()).decode()


def decrypt_text(secret: str, value: str) -> str:
    return _fernet(secret).decrypt(value.encode()).decode()


def create_token(settings: Settings, user_id: str, kind: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.token_hours)
    payload = {"sub": user_id, "kind": kind, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def read_token(settings: Settings, token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


def new_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
