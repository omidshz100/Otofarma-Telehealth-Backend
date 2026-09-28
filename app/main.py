from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.models import User
from app.routes import router
from app.security import hash_password


def _ensure_user_columns(engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "app_password_encrypted" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN app_password_encrypted TEXT"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.database_url.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    _ensure_user_columns(engine)
    factory = make_session_factory(engine)
    db = factory()
    try:
        email = settings.admin_email.lower()
        if db.query(User).filter(User.email == email).one_or_none() is None:
            db.add(
                User(
                    kind="admin",
                    name=settings.admin_name,
                    email=email,
                    password_hash=hash_password(settings.admin_password),
                )
            )
            db.commit()
    finally:
        db.close()

    api = FastAPI(title="Otofarma API")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.state.settings = settings
    api.state.session_factory = factory
    api.include_router(router)
    return api


app = create_app()
