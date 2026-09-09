from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://crm:crm@localhost:5432/crm"
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60
    REFRESH_TOKEN_DAYS: int = 7
    ADMIN_EMAIL: str = "admin@crm.local"
    ADMIN_PASSWORD: str = "Admin123!"
    ADMIN_NAME: str = "Administrator"
    STORAGE_DIR: str = "../storage"
    MAX_UPLOAD_MB: int = 15
    OPEN_LEAD_LIMIT: int = 1
    CORS_ORIGINS: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
