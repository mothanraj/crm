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
    OPEN_LEAD_LIMIT: int = 3
    CORS_ORIGINS: str = "http://localhost:5173"
    FRONTEND_URL: str = "http://localhost:5173"
    # Email via Brevo (transactional). Real key lives in local .env only.
    EMAIL_ENABLED: bool = True
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = ""
    BREVO_SENDER_NAME: str = "E-Star CRM"
    OVERDUE_DIGEST_HOUR: int = 9
    # Google Sheets push sync (Apps Script -> POST /api/sheets/rows).
    SHEETS_WEBHOOK_SECRET: str = ""
    SHEETS_SIGNATURE_WINDOW_SEC: int = 300

    class Config:
        env_file = ".env"


settings = Settings()
