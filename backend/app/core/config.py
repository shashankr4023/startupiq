from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""

    @property
    def SUPABASE_JWKS_URL(self) -> str:
        """Public JSON Web Key Set used to verify Supabase-issued access
        tokens (ES256/RS256). No secret required - these are public keys."""
        return f"{self.SUPABASE_URL}/auth/v1/.well-known/jwks.json"

    # Database (Supavisor *pooler* connection string, used by the running app)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

    # Database (*direct* connection string, used only for Alembic migrations -
    # the transaction-mode pooler doesn't support the prepared statements
    # Alembic/DDL needs)
    DATABASE_URL_DIRECT: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # Redis - used by Arq for the job queue, plus the cache and rate limiter
    REDIS_URL: str = "redis://localhost:6379"

    # Cache time-to-live (seconds)
    CACHE_TTL_IDEA: int = 60
    CACHE_TTL_DASHBOARD: int = 60

    # Rate limits (slowapi syntax). Evaluations are strict (they cost LLM calls).
    RATE_LIMIT_EVALUATION: str = "10/hour"
    RATE_LIMIT_WRITE: str = "60/minute"

    # LLM provider selection: "openai" (dev/testing) or "claude" (production)
    LLM_PROVIDER: str = "openai"

    # OpenAI (used when LLM_PROVIDER == "openai")
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Anthropic / Claude (used when LLM_PROVIDER == "claude")
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"


settings = Settings()
