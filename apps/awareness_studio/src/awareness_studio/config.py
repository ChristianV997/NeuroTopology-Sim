import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

APP_ROOT: Path = Path(__file__).resolve().parent.parent.parent  # apps/awareness_studio/

# ── I/O paths ───────────────────────────────────────────────────────────────
_notion_export_env = os.getenv("NOTION_EXPORT_DIR")
INPUTS_DIR: Path = (
    Path(_notion_export_env) if _notion_export_env else APP_ROOT / "inputs" / "notion_export"
)
INDEX_DIR: Path = APP_ROOT / ".index"
DATA_DIR: Path = APP_ROOT / ".data"

# ── Chunking ────────────────────────────────────────────────────────────────
MAX_CHUNK_CHARS: int = 1200
CHUNK_OVERLAP_CHARS: int = 150

# ── BM25 ────────────────────────────────────────────────────────────────────
BM25_K1: float = 1.5
BM25_B: float = 0.75
DEFAULT_TOP_K: int = 8

# ── Index backend ───────────────────────────────────────────────────────────
INDEX_BACKEND: str = os.getenv("INDEX_BACKEND", "bm25")  # "bm25" | "embedding"

# ── Embeddings ──────────────────────────────────────────────────────────────
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "local_stub")  # "openai" | "local_stub"
OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "64"))  # 64 for stub; 1536 for openai ada

# ── LLM (common) ────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic" | "openai"
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# ── Anthropic ───────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# ── OpenAI ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_TIMEOUT_S: float = float(os.getenv("OPENAI_TIMEOUT_S", "30"))

# ── Prompt optimization ──────────────────────────────────────────────────────
PROMPT_OPTIMIZER: str = os.getenv("PROMPT_OPTIMIZER", "none")  # "none" | "dspy_stub"

# ── Tool router (Phase 3) ────────────────────────────────────────────────────
TOOLS_ENABLED: bool = os.getenv("TOOLS_ENABLED", "false").lower() == "true"
TOOLS_ALLOWLIST: list = [
    t.strip() for t in os.getenv("TOOLS_ALLOWLIST", "").split(",") if t.strip()
]
TOOLS_MAX_CALLS_PER_REQUEST: int = int(os.getenv("TOOLS_MAX_CALLS_PER_REQUEST", "1"))

# ── External API keys (optional) ─────────────────────────────────────────────
LINEAR_API_KEY: str = os.getenv("LINEAR_API_KEY", "")
PUBMED_API_KEY: str = os.getenv("PUBMED_API_KEY", "")  # optional; improves rate limits

# ── Web / CORS ────────────────────────────────────────────────────────────────
CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "")  # e.g. "*" or "https://myapp.com"

# ── Airtable Ops Mirror ───────────────────────────────────────────────────────
AIRTABLE_ENABLED: bool = os.getenv("AIRTABLE_ENABLED", "false").lower() == "true"
AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")

# ── Auth gate (write endpoints) ────────────────────────────────────────────────
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() == "true"
AUTH_API_KEY: str = os.getenv("AUTH_API_KEY", "")

# ── Prompt optimization ──────────────────────────────────────────────────────
PROMPT_OPTIMIZER: str = os.getenv("PROMPT_OPTIMIZER", "none")  # "none" | "dspy_stub"

# ── Tool router (Phase 3) ────────────────────────────────────────────────────
TOOLS_ENABLED: bool = os.getenv("TOOLS_ENABLED", "false").lower() == "true"
TOOLS_ALLOWLIST: list = [
    t.strip() for t in os.getenv("TOOLS_ALLOWLIST", "").split(",") if t.strip()
]
TOOLS_MAX_CALLS_PER_REQUEST: int = int(os.getenv("TOOLS_MAX_CALLS_PER_REQUEST", "1"))

# ── External API keys (optional) ─────────────────────────────────────────────
LINEAR_API_KEY: str = os.getenv("LINEAR_API_KEY", "")
PUBMED_API_KEY: str = os.getenv("PUBMED_API_KEY", "")  # optional; improves rate limits

# ── Web / CORS ────────────────────────────────────────────────────────────────
CORS_ALLOW_ORIGINS: str = os.getenv("CORS_ALLOW_ORIGINS", "")  # e.g. "*" or "https://myapp.com"

# ── Airtable Ops Mirror ───────────────────────────────────────────────────────
AIRTABLE_ENABLED: bool = os.getenv("AIRTABLE_ENABLED", "false").lower() == "true"
AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")

# ── Auth gate (write endpoints) ────────────────────────────────────────────────
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() == "true"
AUTH_API_KEY: str = os.getenv("AUTH_API_KEY", "")

# ── Backward-compat shims ────────────────────────────────────────────────────
LLM_MODEL: str = ANTHROPIC_MODEL if LLM_PROVIDER == "anthropic" else OPENAI_MODEL
LLM_API_KEY: str = ANTHROPIC_API_KEY if LLM_PROVIDER == "anthropic" else OPENAI_API_KEY
