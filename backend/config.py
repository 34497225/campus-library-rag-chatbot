from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str | None = None
    direct_database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")

        return self.database_url