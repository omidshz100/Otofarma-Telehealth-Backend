from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=8, max_length=200)


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=80)
    gmail: EmailStr
    gmail_password: str = Field(min_length=8, max_length=200)
    app_password: str = Field(min_length=8, max_length=200)
    app_ids: list[str] = []


class OwnPasswords(BaseModel):
    gmail_password: str | None = Field(default=None, min_length=8, max_length=200)
    app_password: str | None = Field(default=None, min_length=8, max_length=200)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=80)
    gmail: EmailStr | None = None
    gmail_password: str | None = Field(default=None, min_length=8, max_length=200)
    app_password: str | None = Field(default=None, min_length=8, max_length=200)
    app_ids: list[str] | None = None


class AppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    package_name: str = Field(min_length=3, max_length=200)
    version: str = Field(min_length=1, max_length=40)
    install_method: str
    play_url: str | None = None


class AppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    package_name: str | None = Field(default=None, min_length=3, max_length=200)
    version: str | None = Field(default=None, min_length=1, max_length=40)
    install_method: str | None = None
    play_url: str | None = None


class GuideItem(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    solution: str | None = None
    image_ids: list[str] = []
    video_ids: list[str] = []


class GuideIn(BaseModel):
    overview: list[GuideItem] = []
    setup: list[GuideItem] = []
    usage: list[GuideItem] = []
    problems: list[GuideItem] = []


class InstallItem(BaseModel):
    app_id: str
    installed: bool
    version: str | None = None


class InstallReportIn(BaseModel):
    items: list[InstallItem]


class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=8, max_length=400)
    platform: str = "android"
