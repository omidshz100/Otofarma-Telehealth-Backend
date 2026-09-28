import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    gmail_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    apps: Mapped[list["UserApp"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class App(Base):
    __tablename__ = "apps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    package_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(40))
    install_method: Mapped[str] = mapped_column(String(16))
    play_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    apk_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    apk_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    guide_draft: Mapped[dict] = mapped_column(JSON, default=dict)
    guide_published: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guide_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assignments: Mapped[list["UserApp"]] = relationship(back_populates="app", cascade="all, delete-orphan")


class UserApp(Base):
    __tablename__ = "user_apps"
    __table_args__ = (UniqueConstraint("user_id", "app_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"))

    user: Mapped[User] = relationship(back_populates="apps")
    app: Mapped[App] = relationship(back_populates="assignments")


class Media(Base):
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InstallReport(Base):
    __tablename__ = "install_reports"
    __table_args__ = (UniqueConstraint("user_id", "app_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    installed: Mapped[bool] = mapped_column(Boolean, default=False)
    installed_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(400), unique=True)
    platform: Mapped[str] = mapped_column(String(32), default="android")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    app_id: Mapped[str | None] = mapped_column(ForeignKey("apps.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
