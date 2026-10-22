from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ignore leftover .env keys (e.g. old SHEETS_* after Google Sheets removal).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
    # Email via SMTP. Real credentials live in local .env only.
    EMAIL_ENABLED: bool = True
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_SSL: bool = True
    SMTP_USE_TLS: bool = False
    SMTP_TIMEOUT: int = 30
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "E-Star CRM"
    # Fewer, larger assignment emails cut SMTP handshakes and shared-host rate limits.
    ASSIGNMENT_EMAIL_CHUNK: int = 50
    EMAIL_SESSION_MESSAGE_LIMIT: int = 40
    EMAIL_SEND_ATTEMPTS: int = 3
    # Failed assignment mails are retried quickly instead of waiting for the SLA sweep.
    ASSIGNMENT_RETRY_MINUTES: int = 2
    ASSIGNMENT_EMAIL_GRACE_SECONDS: int = 120
    SLA_SWEEP_MINUTES: int = 5
    OVERDUE_DIGEST_HOUR: int = 9


settings = Settings()
