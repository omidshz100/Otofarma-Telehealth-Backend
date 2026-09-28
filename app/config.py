from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/app.db"
    secret_key: str = "dev-secret-change-me"
    admin_email: str = "admin@example.com"
    admin_password: str = "admin12345"
    admin_name: str = "Admin"
    storage_dir: str = "./storage"
    token_hours: int = 24 * 14
    expose_reset_token: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
