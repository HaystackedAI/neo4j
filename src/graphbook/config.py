"""Application settings, loaded from environment / .env and validated at boot."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Neo4jSettings(BaseSettings):
    """Connection settings for the Neo4j (Aura) instance."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NEO4J_",
        extra="ignore",
    )

    uri: str = Field(description="Bolt URI, e.g. neo4j+s://<id>.databases.neo4j.io")
    username: str = "neo4j"
    password: SecretStr
    database: str = "neo4j"

    @property
    def auth(self) -> tuple[str, str]:
        """Credentials tuple in the shape GraphDatabase.driver() expects."""
        return self.username, self.password.get_secret_value()


class Settings(BaseSettings):
    """Root settings object. One instance per process, via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, building them on first call.

    Cached so the .env file is read once; tests can reset with
    get_settings.cache_clear().
    """
    return Settings()
