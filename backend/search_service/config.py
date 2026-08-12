from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    index_dir: Path = Path(os.getenv("HYBRID_INDEX_DIR", "./semantic-v1"))
    dictionary_root: Path | None = Path(os.environ["HYBRID_DICTIONARY_ROOT"]) if os.getenv("HYBRID_DICTIONARY_ROOT") else None
    model_id: str | None = os.getenv("HYBRID_MODEL_ID") or os.getenv("SEMANTIC_MODEL_ID")
    model_dir: Path | None = (
        Path(os.environ["BGE_M3_MODEL_DIR"])
        if os.getenv("BGE_M3_MODEL_DIR")
        else None
    )
    semantic_enabled: bool = os.getenv("SEMANTIC_ENABLED", "1").lower() not in {"0", "false", "no"}
    timeout_seconds: float = _float("HYBRID_TIMEOUT_SECONDS", 3.2)
    page_size_max: int = _int("HYBRID_PAGE_SIZE_MAX", 40)
    rate_limit_per_minute: int = _int("HYBRID_RATE_LIMIT_PER_MINUTE", 12)
    cache_ttl_seconds: int = _int("HYBRID_CACHE_TTL_SECONDS", 600)
    cache_size: int = _int("HYBRID_CACHE_SIZE", 256)
    rrf_k: int = _int("HYBRID_RRF_K", 60)
    lexical_limit: int = _int("HYBRID_LEXICAL_LIMIT", 200)
    semantic_limit: int = _int("HYBRID_SEMANTIC_LIMIT", 200)


settings = Settings()
