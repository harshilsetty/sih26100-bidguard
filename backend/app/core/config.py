from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Project Info
    PROJECT_NAME: str = "GeM Bid Compliance Verification Platform"
    PROJECT_DESCRIPTION: str = "AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement (SIH26100)"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Server Settings
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    # Database Settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/gem_compliance"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgrespassword@localhost:5432/gem_compliance"
    ALLOW_SQLITE_FALLBACK: bool = False

    # NVIDIA NIM / API Settings
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL: str = "openai/gpt-oss-20b"
    NVIDIA_EMBEDDING_MODEL: str = "nvidia/nemotron-3-embed-1b"
    EMBEDDING_DIM: int = 2048

    # Evidence Retrieval
    DEFAULT_RETRIEVAL_TOP_K: int = 3

    # Uploads & Storage
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 50


settings = Settings()
