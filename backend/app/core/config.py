"""Load environment-specific settings without embedding secrets in code."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Describe the backend runtime configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "ketsip"
    JWT_SECRET: str = ""
    SEED_PASSWORD: str = ""
    SEED_ON_STARTUP: bool = True
    CORS_ORIGINS: str = "http://localhost:5173"
    JWT_EXPIRY_MINUTES: int = 480

    def validate_security(self) -> None:
        """Reject unsafe signing and initial credential configuration."""
        secret = self.JWT_SECRET.strip()
        if len(secret) < 32 or secret.lower() in {"dev-secret-change-in-production", "change-me"}:
            raise RuntimeError("JWT_SECRET must be a unique secret of at least 32 characters")
        if self.SEED_ON_STARTUP and not 12 <= len(self.SEED_PASSWORD.encode()) <= 72:
            raise RuntimeError("SEED_PASSWORD must be 12–72 UTF-8 bytes")
        if self.JWT_EXPIRY_MINUTES <= 0:
            raise RuntimeError("JWT_EXPIRY_MINUTES must be positive")


settings = Settings()
