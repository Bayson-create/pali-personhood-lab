from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .hybrid_core import HybridEngine, build_engine, decode_cursor, encode_cursor, _query_hash

logger = logging.getLogger("sutta.search")


class HybridResponse(BaseModel):
    query: str
    language: str
    mode: str
    total: int
    results: list[dict[str, Any]]
    next_cursor: str | None = None
    semantic: dict[str, Any]
    request_id: str | None = None


class TTLCache:
    def __init__(self, maxsize: int, ttl: int):
        self.maxsize = maxsize
        self.ttl = ttl
        self.items: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    def get(self, key: str) -> dict[str, Any] | None:
        value = self.items.get(key)
        if not value:
            return None
        expires, payload = value
        if expires <= time.monotonic():
            self.items.pop(key, None)
            return None
        self.items.move_to_end(key)
        return payload

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.items[key] = (time.monotonic() + self.ttl, value)
        self.items.move_to_end(key)
        while len(self.items) > self.maxsize:
            self.items.popitem(last=False)


class RateLimiter:
    def __init__(self, limit: int):
        self.limit = limit
        self.calls: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        calls = self.calls[key]
        while calls and now - calls[0] >= 60:
            calls.popleft()
        if len(calls) >= self.limit:
            return False
        calls.append(now)
        return True


def _split(value: str | None, separators: str = ",|") -> tuple[str, ...]:
    if not value:
        return ()
    result = value
    for separator in separators:
        result = result.replace(separator, " ")
    return tuple(dict.fromkeys(item.strip() for item in result.split() if item.strip()))


def create_app(engine: HybridEngine | None = None) -> FastAPI:
    app = FastAPI(title="Sutta Hybrid Search", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[item.strip() for item in __import__("os").getenv("HYBRID_CORS_ORIGINS", "https://bayson-create.github.io,http://localhost:8080,http://localhost:4173").split(",") if item.strip()],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.engine = engine or build_engine(
        settings.index_dir,
        model_id=(settings.model_id or (str(settings.model_dir) if settings.model_dir else None)) if settings.semantic_enabled else None,
        dictionary_root=settings.dictionary_root,
        rrf_k=settings.rrf_k,
        lexical_limit=settings.lexical_limit,
        semantic_limit=settings.semantic_limit,
    )
    app.state.lexical_engine = HybridEngine(
        app.state.engine.index,
        rrf_k=settings.rrf_k,
        model_id=None,
        lexical_limit=settings.lexical_limit,
        semantic_limit=0,
    )
    app.state.cache = TTLCache(settings.cache_size, settings.cache_ttl_seconds)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    @app.get("/healthz")
    async def healthz():
        status = app.state.engine.index.status()
        status["service"] = "ready" if status["loaded"] else "degraded"
        status["semantic"]["runtime_enabled"] = settings.semantic_enabled
        return status

    @app.get("/api/search/v1/hybrid", response_model=HybridResponse)
    async def hybrid(
        request: Request,
        q: str = Query(..., min_length=1, max_length=200),
        corpora: str = Query("early_buddhist,v4"),
        scopes: str | None = Query(None),
        resource_types: str | None = Query(None),
        language: str = Query("zh", pattern="^(zh|en|pali)$"),
        mode: str = Query("explore", pattern="^(precise|explore)$"),
        page_size: int = Query(40, ge=1, le=settings.page_size_max),
        cursor: str | None = Query(None),
    ):
        client = request.client.host if request.client else "unknown"
        if not app.state.rate_limiter.allow(client):
            raise HTTPException(status_code=429, detail="rate limit exceeded", headers={"Retry-After": "60"})
        normalized = " ".join(q.split())
        corpus_values = _split(corpora)
        scope_values = _split(scopes)
        type_values = _split(resource_types)
        if any(value not in {"early_buddhist", "v4"} for value in corpus_values):
            raise HTTPException(status_code=400, detail="unsupported corpus")
        expected_hash = _query_hash(normalized, language, corpus_values, scope_values, type_values)
        offset = 0
        if cursor:
            try:
                payload = decode_cursor(cursor)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if payload.get("query_hash") != expected_hash or payload.get("version") != app.state.engine.index.manifest.get("version"):
                raise HTTPException(status_code=409, detail="cursor does not match the current query or index")
            offset = int(payload.get("offset", 0))
        cache_key = hashlib.sha256(f"{expected_hash}:{mode}:{page_size}:{offset}".encode()).hexdigest()
        started = time.perf_counter()
        cached = app.state.cache.get(cache_key)
        if cached is not None:
            return cached

        kwargs = dict(language=language, corpora=corpus_values, scopes=scope_values, resource_types=type_values, mode=mode, page_size=page_size, offset=offset)
        try:
            data = await asyncio.wait_for(asyncio.to_thread(app.state.engine.search, normalized, **kwargs), timeout=settings.timeout_seconds)
        except Exception as exc:
            # A semantic model or shard may be unavailable. The lexical path
            # is still useful, but its fallback has its own short deadline so
            # the browser never waits beyond the contractual 3.5 seconds.
            try:
                data = await asyncio.wait_for(asyncio.to_thread(app.state.lexical_engine.search, normalized, **kwargs), timeout=min(1.0, settings.timeout_seconds))
            except Exception as fallback_exc:
                data = {"query": normalized, "language": language, "mode": mode, "total": 0, "results": [], "semantic": {"enabled": False, "degraded": True, "reason": f"{type(exc).__name__};fallback:{type(fallback_exc).__name__}"}}
            else:
                data["semantic"] = {"enabled": False, "degraded": True, "reason": type(exc).__name__}
        next_offset = data.pop("next_offset", None)
        data["next_cursor"] = encode_cursor({"version": app.state.engine.index.manifest.get("version"), "query_hash": expected_hash, "offset": next_offset}) if next_offset is not None else None
        data["request_id"] = str(uuid.uuid4())
        app.state.cache.set(cache_key, data)
        logger.info("hybrid_search", extra={"query_hash": expected_hash, "language": language, "mode": mode, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "degraded": bool(data.get("semantic", {}).get("degraded")), "result_count": len(data.get("results", []))})
        return data

    return app


app = create_app()
