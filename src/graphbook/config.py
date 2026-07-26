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


class BedrockSettings(BaseSettings):
    """Region and model choices for AWS Bedrock.

    No credentials here on purpose: boto3 resolves those itself from the
    standard chain (env vars, shared config, SSO, instance role). Copying them
    into .env would just add a second, staler source of truth.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BEDROCK_",
        extra="ignore",
    )

    region: str = Field(
        default="us-east-1",
        description="Bedrock region. Not a secret, so it lives here, not in .env.",
    )
    text_model: str = Field(
        default="amazon.nova-micro-v1:0",
        description="Model for the patent summaries (Ch6). Cheapest Nova tier.",
    )
    embedding_model: str = Field(
        default="amazon.titan-embed-text-v2:0",
        description="Model for summary embeddings (Ch6/Ch7).",
    )
    embedding_dimensions: int = Field(
        default=1024,
        description=(
            "Titan v2 emits 1024 by default; 512 and 256 are also supported. "
            "Must match the dimension declared on the Neo4j vector index."
        ),
    )


class Settings(BaseSettings):
    """Root settings object. One instance per process, via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    bedrock: BedrockSettings = Field(default_factory=BedrockSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, building them on first call.

    Cached so the .env file is read once; tests can reset with
    get_settings.cache_clear().
    """
    return Settings()
