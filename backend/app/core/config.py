from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secrets that must never be accepted in production.
_UNSAFE_JWT_SECRETS = {
    "",
    "your-super-secret-jwt-key-change-in-production",
    "your-super-secret-jwt-key-change-in-production-min-32-chars",
    "change-me",
    "changeme",
    "secret",
    "test",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "CampusXolve AI"
    APP_DESCRIPTION: str = "AI-Powered Campus Problem Solving"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|test|production)$")
    DEBUG: bool = True

    # API
    API_PREFIX: str = "/api/v1"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve",
        description="PostgreSQL async connection URL",
    )
    DATABASE_ECHO: bool = False
    # Isolated database for pytest. When set (or derived as campusxolve_test),
    # the test suite runs entirely here and never touches DATABASE_URL.
    TEST_DATABASE_URL: str | None = Field(
        default=None,
        description="PostgreSQL async connection URL for the test suite",
    )

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"

    # CORS (JSON array in .env, e.g. ["http://localhost:3000"]; a single
    # comma-separated string is also accepted and split automatically)
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001"],
        description="Allowed CORS origins",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Accept both JSON arrays and comma-separated strings from .env files."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_strong_production_secret(self) -> "Settings":
        """Refuse to boot production with a placeholder or short JWT secret."""
        if self.ENVIRONMENT == "production":
            secret = (self.JWT_SECRET_KEY or "").strip()
            if secret in _UNSAFE_JWT_SECRETS or len(secret) < 32:
                raise ValueError(
                    "ENVIRONMENT=production requires JWT_SECRET_KEY to be a "
                    "non-default secret of at least 32 characters."
                )
            frontend = (self.FRONTEND_URL or "").strip()
            if not (frontend.startswith("https://") or frontend.startswith("http://")):
                raise ValueError(
                    "ENVIRONMENT=production requires FRONTEND_URL to be an explicit "
                    "http(s) URL (no bare hostnames)."
                )
            if "*" in self.CORS_ORIGINS:
                raise ValueError(
                    "ENVIRONMENT=production forbids '*' in CORS_ORIGINS when "
                    "credentials (refresh cookie) are enabled."
                )
        return self

    def cors_allow_methods(self) -> list[str]:
        """Broad in development; explicit allowlist in production."""
        if self.ENVIRONMENT == "production":
            return ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]
        return ["*"]

    def cors_allow_headers(self) -> list[str]:
        if self.ENVIRONMENT == "production":
            return ["Authorization", "Content-Type", "Accept", "X-Request-ID"]
        return ["*"]

    # JWT (for future auth implementation)
    JWT_SECRET_KEY: str = Field(
        default="your-super-secret-jwt-key-change-in-production",
        description="Secret key for JWT token signing",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Logging
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # Problem attachments (local storage; swappable for S3/Cloudinary later)
    STORAGE_DIR: str = Field(
        default="storage/problem-attachments",
        description="Directory for locally stored problem attachments (relative to backend/)",
    )
    MAX_ATTACHMENT_SIZE_MB: int = Field(default=10, gt=0)
    MAX_ATTACHMENTS_PER_PROBLEM: int = Field(default=5, gt=0)
    ALLOWED_ATTACHMENT_MIME_TYPES: list[str] = Field(
        default=["image/jpeg", "image/png", "image/webp", "application/pdf"],
        description="Allowed MIME types for problem attachments",
    )

    # AI problem classification (Step 5: DistilBERT, local inference)
    CLASSIFICATION_MODEL_DIR: str = Field(
        default="ml/artifacts/problem_classifier",
        description="Trained classifier artifact dir (relative to backend/)",
    )
    CLASSIFICATION_CONFIDENCE_THRESHOLD: float = Field(default=0.60, ge=0.0, le=1.0)

    # Priority scoring (Step 6: explainable weighted engine v1)
    PRIORITY_LOW_MAX: int = Field(default=29, ge=0, le=100)
    PRIORITY_MEDIUM_MAX: int = Field(default=54, ge=0, le=100)
    PRIORITY_HIGH_MAX: int = Field(default=79, ge=0, le=100)

    # Required skill extraction (Step 6: hybrid exact + Sentence-BERT)
    SKILL_EMBEDDING_MODEL: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    SKILL_EMBEDDING_VERSION: str = Field(default="campusxolve-skill-embeddings-v1")
    SKILL_EXTRACTOR_VERSION: str = Field(default="campusxolve-skill-extractor-v1")
    SKILL_SIMILARITY_THRESHOLD: float = Field(default=0.45, ge=0.0, le=1.0)
    SKILL_MAX_RESULTS: int = Field(default=6, ge=1, le=20)

    # Duplicate detection (Step 7: semantic + pgvector)
    PROBLEM_EMBEDDING_VERSION: str = Field(default="campusxolve-problem-embedding-v1")
    DUPLICATE_ALGORITHM_VERSION: str = Field(default="campusxolve-duplicate-detector-v1")
    DUPLICATE_CANDIDATE_THRESHOLD: float = Field(default=0.60, ge=0.0, le=1.0)
    DUPLICATE_STRONG_THRESHOLD: float = Field(default=0.82, ge=0.0, le=1.0)
    DUPLICATE_CANDIDATE_LIMIT: int = Field(default=5, ge=1, le=20)
    DUPLICATE_SEMANTIC_WEIGHT: float = Field(default=0.85, ge=0.0, le=1.0)
    DUPLICATE_LOCATION_WEIGHT: float = Field(default=0.10, ge=0.0, le=1.0)
    DUPLICATE_CATEGORY_WEIGHT: float = Field(default=0.05, ge=0.0, le=1.0)

    # Team recommendation (Step 8: deterministic team combinations, v1)
    TEAM_ALGORITHM_VERSION: str = Field(default="campusxolve-team-recommender-v1")
    TEAM_MIN_SIZE: int = Field(default=2, ge=1, le=8)
    TEAM_MAX_SIZE: int = Field(default=4, ge=1, le=8)
    TEAM_ALLOW_SOLO: bool = Field(default=False)
    TEAM_NUM_OPTIONS: int = Field(default=3, ge=1, le=5)
    TEAM_CANDIDATE_POOL: int = Field(default=12, ge=1, le=50)
    TEAM_WEIGHT_COVERAGE: float = Field(default=50.0, ge=0.0, le=100.0)
    TEAM_WEIGHT_PROFICIENCY: float = Field(default=20.0, ge=0.0, le=100.0)
    TEAM_WEIGHT_AVAILABILITY: float = Field(default=10.0, ge=0.0, le=100.0)
    TEAM_WEIGHT_WORKLOAD: float = Field(default=10.0, ge=0.0, le=100.0)
    TEAM_WEIGHT_VERIFIED: float = Field(default=5.0, ge=0.0, le=100.0)
    TEAM_WEIGHT_DOMAIN: float = Field(default=5.0, ge=0.0, le=100.0)

    # Rate limiting (Step 15: in-memory sliding window; see app/middleware).
    # Disabled automatically when ENVIRONMENT == "test".
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = Field(default=600, gt=0)
    RATE_LIMIT_AUTH_PER_MINUTE: int = Field(default=20, gt=0)
    RATE_LIMIT_UPLOAD_PER_MINUTE: int = Field(default=30, gt=0)
    RATE_LIMIT_AI_PER_MINUTE: int = Field(default=60, gt=0)
    RATE_LIMIT_SEARCH_PER_MINUTE: int = Field(default=120, gt=0)

    # Mentor recommendation (Step 8: semantic + skill match, v1)
    MENTOR_ALGORITHM_VERSION: str = Field(default="campusxolve-mentor-recommender-v1")
    MENTOR_WEIGHT_SPECIALIZATION: float = Field(default=35.0, ge=0.0, le=100.0)
    MENTOR_WEIGHT_SKILL: float = Field(default=30.0, ge=0.0, le=100.0)
    MENTOR_WEIGHT_CATEGORY: float = Field(default=15.0, ge=0.0, le=100.0)
    MENTOR_WEIGHT_AVAILABILITY: float = Field(default=10.0, ge=0.0, le=100.0)
    MENTOR_WEIGHT_WORKLOAD: float = Field(default=10.0, ge=0.0, le=100.0)

    # Knowledge Repository (Step 12: verified solved problems, MiniLM-384).
    # The embedding MODEL is always the shared all-MiniLM-L6-v2 singleton
    # (SKILL_EMBEDDING_MODEL); only the version tag below is knowledge-specific.
    KNOWLEDGE_EMBEDDING_VERSION: str = Field(
        default="campusxolve-knowledge-embedding-v1"
    )
    KNOWLEDGE_SEMANTIC_MIN_SCORE: float = Field(default=0.35, ge=0.0, le=1.0)
    KNOWLEDGE_SEARCH_LIMIT: int = Field(default=10, ge=1, le=50)
    KNOWLEDGE_HYBRID_SEMANTIC_WEIGHT: float = Field(default=0.75, ge=0.0, le=1.0)
    KNOWLEDGE_HYBRID_KEYWORD_WEIGHT: float = Field(default=0.25, ge=0.0, le=1.0)


settings = Settings()
