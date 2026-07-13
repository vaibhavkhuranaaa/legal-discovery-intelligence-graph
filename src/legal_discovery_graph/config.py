"""Application configuration.

All configuration is parsed exactly once into ``Settings`` and accessed
exclusively through :func:`get_settings`. Application code must never read
``os.environ`` directly — every module receives configuration via
``get_settings()`` or as an injected parameter.

Secrets are supplied through environment variables (locally via ``.env``,
in deployment via Streamlit secrets mapped to environment variables). No
credentials are ever hardcoded or committed.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Legal Discovery Intelligence Graph.

    All connection values default to empty strings so the package imports
    cleanly without any environment configured (e.g. during tests). Code
    that requires a live backend must validate the relevant fields are
    populated before connecting.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL + pgvector (Supabase-hosted in deployment)
    database_url: str = ""

    # Neo4j AuraDB
    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = ""

    # Embeddings
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Application behavior
    app_env: str = "development"
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
