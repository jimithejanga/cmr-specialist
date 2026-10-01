"""Configuration settings for the Ogun LLM Harness."""
import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Field(default_factory=lambda: Path(os.getenv("HARNESS_DATA_DIR", Path(__file__).resolve().parent.parent / "data")))
    KNOWLEDGE_DIR: Path = Field(default_factory=lambda: Path(os.getenv("HARNESS_KNOWLEDGE_DIR", Path(__file__).resolve().parent.parent / "data" / "knowledge")))
    PROCEDURES_DIR: Path = Field(default_factory=lambda: Path(os.getenv("HARNESS_PROCEDURES_DIR", Path(__file__).resolve().parent.parent / "data" / "procedures")))
    SQLITE_DB_PATH: Path = Field(default_factory=lambda: Path(os.getenv("HARNESS_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "harness.db")))
    VECTOR_INDEX_DIR: Path = Field(default_factory=lambda: Path(os.getenv("HARNESS_VECTOR_DIR", Path(__file__).resolve().parent.parent / "data" / "vector_index")))

    # Database — PostgreSQL is the system of record; SQLite is the local fallback.
    # Live state lives in var/ (never committed). Set DATABASE_URL explicitly
    # to override, e.g. DATABASE_URL=postgresql+psycopg://user:pass@host:5432/cmr
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.getenv('HARNESS_DB_PATH', str(Path(__file__).resolve().parent.parent / 'var' / 'cmr_cases.db'))}",
    )

    # Embedding Model Settings
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5")
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cpu")

    # Retrieval Settings
    KNOWLEDGE_TOP_K: int = int(os.getenv("KNOWLEDGE_TOP_K", "4"))
    PROCEDURE_TOP_K: int = int(os.getenv("PROCEDURE_TOP_K", "4"))

    # Memory Settings
    MAX_MEMORY_TURNS: int = int(os.getenv("MAX_MEMORY_TURNS", "6"))

    # Inference Gateway Settings
    INFERENCE_PROVIDER: str = os.getenv("INFERENCE_PROVIDER", "mock")  # mock | gemini | openrouter | http | local_qwen
    INFERENCE_HTTP_URL: str = os.getenv("INFERENCE_HTTP_URL", "http://localhost:8000/v1/chat/completions")
    INFERENCE_API_KEY: str = os.getenv("INFERENCE_API_KEY", "")
    INFERENCE_MODEL: str = os.getenv("INFERENCE_MODEL", "")
    # Gemini (OpenAI-compatible endpoint; Bearer = GEMINI_API_KEY)
    GEMINI_API_URL: str = os.getenv(
        "GEMINI_API_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    # OpenRouter (OpenAI-compatible; Bearer = OPENROUTER_API_KEY; any model id)
    OPENROUTER_API_URL: str = os.getenv(
        "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    OPENROUTER_SITE_URL: str = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8080")
    OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "CMR-Specialist")

    # Token budget controls (pacing + caching; never gating — model always decides)
    LLM_MIN_INTERVAL_S: float = float(os.getenv("LLM_MIN_INTERVAL_S", "2.0"))
    LLM_CACHE_TTL_S: int = int(os.getenv("LLM_CACHE_TTL_S", "600"))
    INFERENCE_TIMEOUT: int = int(os.getenv("INFERENCE_TIMEOUT", "180"))
    INTENT_ROUTER_TIMEOUT: int = int(os.getenv("INTENT_ROUTER_TIMEOUT", "30"))
    QWEN_MODEL_ID: str = os.getenv("QWEN_MODEL_ID", "Qwen/Qwen3-4B-Instruct-2507")
    ADAPTER_PATH: str = os.getenv("ADAPTER_PATH", "")
    USE_4BIT: bool = os.getenv("USE_4BIT", "1").lower() not in {"0", "false", "no"}

    # API Settings
    HARNESS_API_KEY: str = os.getenv("HARNESS_API_KEY", "cmr-secret-key-2026")
    TOOL_MODULE_TOKEN: str = os.getenv("TOOL_MODULE_TOKEN", "cmr-tool-token-dev")
    # Shed/pilot locks: STRICT_AUTH=1 fails closed (missing/invalid creds
    # rejected everywhere; approvals need a session user; default secrets
    # refused at startup). Default 0 keeps local-dev ergonomics.
    STRICT_AUTH: bool = os.getenv("STRICT_AUTH", "0").lower() not in {"0", "false", "no"}
    HOST: str = os.getenv("HARNESS_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("HARNESS_PORT", "8080"))

    # Mock CMR registry: separate database + backend switch. Pilot runs the
    # legacy dict backend; MOCKDB_BACKEND=relational points the module at the
    # relational registry (REGISTRY_DATABASE_URL, default var/registry.db).
    MOCKDB_BACKEND: str = os.getenv("MOCKDB_BACKEND", "relational")
    REGISTRY_DATABASE_URL: str = os.getenv(
        "REGISTRY_DATABASE_URL",
        f"sqlite:///{Path(__file__).resolve().parent.parent / 'var' / 'registry.db'}",
    )

    # Lean spec (v2.0) — agent harness / worker / retrieval controls
    APP_VERSION: str = os.getenv("APP_VERSION", "2.0.0")
    MAX_INPUT_CHARS: int = int(os.getenv("MAX_INPUT_CHARS", "6000"))
    MAX_ATTACHMENT_BYTES: int = int(os.getenv("MAX_ATTACHMENT_BYTES", str(10 * 1024 * 1024)))
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    RETRIEVAL_MIN_SCORE: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.05"))
    MAX_PLAN_STEPS: int = int(os.getenv("MAX_PLAN_STEPS", "6"))
    TOOL_DEFAULT_TIMEOUT_S: int = int(os.getenv("TOOL_DEFAULT_TIMEOUT_S", "60"))
    TOOL_MAX_RETRIES: int = int(os.getenv("TOOL_MAX_RETRIES", "2"))
    WORKER_POLL_INTERVAL_S: float = float(os.getenv("WORKER_POLL_INTERVAL_S", "2.0"))
    WORKER_JOB_TIMEOUT_S: int = int(os.getenv("WORKER_JOB_TIMEOUT_S", "600"))
    WORKER_CONCURRENCY: int = int(os.getenv("WORKER_CONCURRENCY", "2"))
    LOG_PII_MASKING: bool = os.getenv("LOG_PII_MASKING", "1").lower() not in {"0", "false", "no"}


settings = Settings()


# Defaults that STRICT_AUTH refuses to run with (fail fast, not fail open).
DEFAULT_API_KEY = "cmr-secret-key-2026"
DEFAULT_TOOL_TOKEN = "cmr-tool-token-dev"


def strict_auth() -> bool:
    """Live env read so tests can toggle per-case (field is import-time)."""
    return os.getenv("STRICT_AUTH", "0").lower() not in {"0", "false", "no"}


def assert_pilot_secrets() -> None:
    """Called at web/worker startup: default secrets + STRICT_AUTH = refuse."""
    from configs.settings import settings as _s

    if strict_auth() and (_s.HARNESS_API_KEY == DEFAULT_API_KEY
                          or _s.TOOL_MODULE_TOKEN == DEFAULT_TOOL_TOKEN):
        raise RuntimeError("STRICT_AUTH=1 with default secrets: set HARNESS_API_KEY "
                           "and TOOL_MODULE_TOKEN to fresh values.")
