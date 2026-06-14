from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://social:social_dev_password@localhost:5432/social_fastapi"
    JWT_SECRET_KEY: str = "insecure-dev-key"
    JWT_ACCESS_TTL_MIN: int = 15
    JWT_REFRESH_TTL_DAYS: int = 7
    CODE_TTL_MINUTES: int = 10
    CODE_MAX_ATTEMPTS: int = 5
    ENV: str = "dev"
    NOTIFIER: str = "console"
    CORS_ORIGINS: str = "http://fastapi.localhost"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
