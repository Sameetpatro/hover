from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hover_addr: str = "0.0.0.0:8000"
    use_sqlite: bool = True
    sqlite_path: str = str(ROOT / "backend" / "hover.db")
    use_local_storage: bool = True
    worker_eager: bool = True

    postgres_db: str = "hover"
    postgres_user: str = "hover"
    postgres_password: str = "hover"
    postgres_host: str = "localhost"
    postgres_port: str = "5432"
    database_url: str = ""

    redis_url: str = "redis://localhost:6379/0"
    media_root: str = str(ROOT / "backend" / "media")
    extract_root: str = str(ROOT / "backend" / "extracted")

    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_storage_bucket_name: str = "hover"
    aws_s3_endpoint_url: str = "http://localhost:9000"
    aws_s3_region_name: str = "us-east-1"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_chat_model: str = "openai/gpt-4o-mini"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    openrouter_http_referer: str = "http://localhost:5173"
    openrouter_app_title: str = "Hover"
    embedding_dim: int = 1536

    max_zip_bytes: int = 200 * 1024 * 1024
    max_extracted_files: int = 5000

    @property
    def sqlalchemy_url(self) -> str:
        # Prefer DATABASE_URL (Neon / Render / etc.)
        url = (self.database_url or "").strip()
        if url:
            # Neon gives postgresql://... — SQLAlchemy + psycopg needs this driver prefix
            if url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://") :]
            elif url.startswith("postgres://"):
                url = "postgresql+psycopg://" + url[len("postgres://") :]
            return url
        if self.use_sqlite:
            return f"sqlite:///{self.sqlite_path}"
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def llm_ready(self) -> bool:
        return bool(self.openrouter_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    Path(s.media_root).mkdir(parents=True, exist_ok=True)
    Path(s.extract_root).mkdir(parents=True, exist_ok=True)
    Path(s.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    return s
