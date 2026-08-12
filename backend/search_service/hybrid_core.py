from __future__ import annotations

import base64
import gzip
import hashlib
import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .dictionary_hydration import DictionaryHydrator
from .model_adapter import Encoder, EncoderUnavailable, build_encoder
from .records import Record

try:  # OpenCC is optional for local unit tests.
    from opencc import OpenCC

    _T2S = OpenCC("t2s")
except Exception:  # pragma: no cover - dependency/environment dependent
    _T2S = None


WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]+")
CJK_RE = re.compile(r"[\u3400-\u9fff]")


def to_simplified(value: str) -> str:
    return _T2S.convert(value) if _T2S else value


def normalize_pali(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower())
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn")


def tokens(value: str, language: str) -> list[str]:
    value = value or ""
    if language == "zh":
        compact = "".join(to_simplified(value).split())
        chars = [ch for ch in compact if CJK_RE.match(ch)]
        # Keep unigrams for terminology and add bigrams for phrase locality.
        # This avoids losing a one-character query while retaining useful
        # matching for Chinese text without an external segmenter.
        bigrams = ["".join(chars[i : i + 2]) for i in range(len(chars) - 1)]
        return list(dict.fromkeys(chars + bigrams))
    words = [match.group() for match in WORD_RE.finditer(value)]
    if language == "pali":
        return list(dict.fromkeys(normalize_pali(word) for word in words))
    return list(dict.fromkeys(word.lower() for word in words))


def _bucket(term: str, buckets: int = 256) -> int:
    return int.from_bytes(hashlib.sha256(term.encode("utf-8")).digest()[:4], "big") % buckets


def _record_bucket(locator: str, buckets: int = 256) -> int:
    return _bucket(locator, buckets)


def _query_hash(query: str, language: str, corpora: tuple[str, ...], scopes: tuple[str, ...], resource_types: tuple[str, ...]) -> str:
    payload = json.dumps([query, language, corpora, scopes, resource_types], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _locator_in_corpora(locator: str, corpora: tuple[str, ...]) -> bool:
    """Match persisted locator namespaces to public corpus names.

    Early-Buddhist locators intentionally use the compact ``early:`` prefix;
    the API corpus name is ``early_buddhist``.  Comparing the strings directly
    silently returned zero results for a correctly built Early index.
    """
    prefixes = {
        "early_buddhist": ("early:",),
        "v4": ("v4:", "dictionary:"),
    }
    return any(locator.startswith(prefix) for corpus in corpora for prefix in prefixes.get(corpus, ()))


def encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> dict[str, Any]:
    padding = "=" * (-len(value) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode((value + padding).encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc


@dataclass(slots=True)
class Candidate:
    locator: str
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    reasons: set[str] | None = None

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = set()


class SearchIndex:
    """Read-only index loader.

    The preferred layout shards both postings and records.  A single
    ``records.jsonl.gz`` is also accepted for tiny fixtures and migration
    tests, but is deliberately not produced by the full builder.
    """

    def __init__(self, root: Path, dictionary_root: Path | None = None):
        self.root = root
        self.manifest: dict[str, Any] = {}
        self.records: dict[str, Record] = {}
        self._record_shards: dict[int, Path] = {}
        self._posting_cache: dict[tuple[str, int], dict[str, list[str]]] = {}
        self._record_cache: dict[int, dict[str, Record]] = {}
        self._semantic = None
        self._semantic_locators: list[str] = []
        self._encoder: Encoder | None = None
        configured_dictionary_root = dictionary_root or (Path(os.environ["HYBRID_DICTIONARY_ROOT"]) if os.getenv("HYBRID_DICTIONARY_ROOT") else root)
        self.dictionary = DictionaryHydrator(configured_dictionary_root)
        self._load_manifest()

    def _load_manifest(self) -> None:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for path in (self.root / "records").glob("shard_*.json.gz"):
            try:
                self._record_shards[int(path.stem.split("_")[-1].split(".")[0])] = path
            except ValueError:
                continue
        self._load_legacy_records()

    def _load_legacy_records(self) -> None:
        path = self.root / "records.jsonl.gz"
        if not path.exists():
            return
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = Record.from_dict(json.loads(line))
                    self.records[record.locator] = record

    def _load_record_shard(self, bucket: int) -> dict[str, Record]:
        if bucket in self._record_cache:
            return self._record_cache[bucket]
        result: dict[str, Record] = {}
        path = self._record_shards.get(bucket)
        if path and path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        record = Record.from_dict(json.loads(line))
                        result[record.locator] = record
        self._record_cache[bucket] = result
        return result

    def get_record(self, locator: str) -> Record | None:
        if locator in self.records:
            return self.records[locator]
        return self._load_record_shard(_record_bucket(locator)).get(locator)

    def _load_postings(self, language: str, bucket: int) -> dict[str, list[str]]:
        key = (language, bucket)
        if key in self._posting_cache:
            return self._posting_cache[key]
        path = self.root / "lexical" / language / f"shard_{bucket:03d}.json.gz"
        result: dict[str, list[str]] = {}
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                result = json.load(handle)
        self._posting_cache[key] = result
        return result

    def _scope_match(self, record: Record, scopes: tuple[str, ...], resource_types: tuple[str, ...], corpora: tuple[str, ...]) -> bool:
        if corpora and record.corpus not in corpora:
            return False
        if resource_types and record.resource_type not in resource_types:
            return False
        if not scopes:
            return True
        path = " / ".join(record.path)
        return any(scope == record.work_id or scope == path or path.startswith(scope + " / ") for scope in scopes)

    def lexical(self, query: str, language: str, *, corpora: tuple[str, ...], scopes: tuple[str, ...], resource_types: tuple[str, ...], limit: int) -> list[Candidate]:
        query_terms = tokens(query, language)
        if not query_terms:
            return []
        if resource_types and "dictionary" in resource_types:
            hydrated = [record for record in self.dictionary.search(query, language, limit=limit) if self._scope_match(record, scopes, resource_types, corpora)]
            candidates = []
            for rank, record in enumerate(hydrated, 1):
                self.records[record.locator] = record
                score = 1.0 / rank + (0.5 if rank == 1 else 0.0)
                candidates.append(Candidate(record.locator, lexical_score=score, lexical_rank=rank, reasons={"??????", "????"}))
            return candidates
        postings: dict[str, set[str]] = {}
        for term in query_terms:
            bucket = _bucket(term)
            values = self._load_postings(language, bucket).get(term, [])
            postings[term] = set(values)

        if not self.records and not self._record_shards:
            return []
        universe = set().union(*postings.values()) if postings else set()
        n = max(1, int(self.manifest.get("record_count", len(self.records) or len(universe))))
        scored: list[Candidate] = []
        # Corpus/resource filters encoded by the canonical locator avoid
        # inflating every record shard on a cold query. Full records are
        # hydrated only when a scope or non-corpus type needs inspection.
        cheap_filter = not scopes and (not resource_types or resource_types == ("corpus",))
        for locator in universe:
            if cheap_filter:
                if corpora and not _locator_in_corpora(locator, corpora):
                    continue
                if resource_types == ("corpus",) and locator.startswith("dictionary:"):
                    continue
                record = None
            else:
                record = self.get_record(locator)
                if not record or not self._scope_match(record, scopes, resource_types, corpora):
                    continue
            matched = [term for term, values in postings.items() if locator in values]
            score = 0.0
            for term in matched:
                df = max(1, len(postings[term]))
                score += math.log1p((n - df + 0.5) / (df + 0.5))
            if len(matched) == len(query_terms):
                score += 0.5
            scored.append(Candidate(locator, lexical_score=score, reasons={"词法命中", "短语/邻近"} if len(matched) > 1 else {"词法命中"}))
        scored.sort(key=lambda item: (-item.lexical_score, item.locator))
        for rank, item in enumerate(scored[:limit], 1):
            item.lexical_rank = rank
        return scored[:limit]

    def _load_semantic(self, model_id: str | None, max_length: int = 384) -> None:
        if self._semantic is not None or not (self.root / "semantic.index").exists():
            return
        try:
            import faiss

            self._semantic = faiss.read_index(str(self.root / "semantic.index"))
            locators_path = self.root / "semantic.locators.json.gz"
            with gzip.open(locators_path, "rt", encoding="utf-8") as handle:
                self._semantic_locators = json.load(handle)
            if model_id:
                self._encoder = build_encoder(model_id, max_length=max_length)
        except (ImportError, OSError, EncoderUnavailable, ValueError):
            self._semantic = None
            self._encoder = None

    def semantic(self, query: str, language: str, *, corpora: tuple[str, ...], scopes: tuple[str, ...], resource_types: tuple[str, ...], limit: int, model_id: str | None) -> list[Candidate]:
        self._load_semantic(model_id)
        if self._semantic is None or self._encoder is None:
            return []
        try:
            vector = self._encoder.encode_queries([query])
            scores, ids = self._semantic.search(vector, limit)
        except Exception:
            return []
        out: list[Candidate] = []
        for score, index in zip(scores[0], ids[0]):
            if index < 0 or index >= len(self._semantic_locators):
                continue
            locator = self._semantic_locators[index]
            record = self.get_record(locator)
            if not record or not self._scope_match(record, scopes, resource_types, corpora):
                continue
            out.append(Candidate(locator, semantic_score=float(score), reasons={"语义相关"}))
        for rank, item in enumerate(out, 1):
            item.semantic_rank = rank
        return out

    @property
    def semantic_ready(self) -> bool:
        return (self.root / "semantic.index").exists() and bool(self.manifest.get("semantic", {}).get("enabled"))

    def status(self) -> dict[str, Any]:
        semantic = self.manifest.get("semantic", {})
        return {
            "loaded": bool(self.manifest),
            "index_version": self.manifest.get("version"),
            "record_count": self.manifest.get("record_count", len(self.records)),
            "semantic": {"enabled": bool(semantic.get("enabled")) and self.semantic_ready, "model": semantic.get("model"), "dimension": semantic.get("dimension")},
            "dictionary": {"available": self.dictionary.available, "mode": "on-demand"},
        }


def rrf_merge(lexical: Iterable[Candidate], semantic: Iterable[Candidate], *, k: int = 60) -> dict[str, Candidate]:
    merged: dict[str, Candidate] = {}
    for branch, values in (("lexical", lexical), ("semantic", semantic)):
        for rank, item in enumerate(values, 1):
            current = merged.setdefault(item.locator, Candidate(item.locator))
            current.rrf_score += 1.0 / (k + rank)
            if branch == "lexical":
                current.lexical_score = item.lexical_score
                current.lexical_rank = rank
            else:
                current.semantic_score = item.semantic_score
                current.semantic_rank = rank
            current.reasons.update(item.reasons or set())
    for item in merged.values():
        item.rerank_score = item.rrf_score
        if item.lexical_rank is not None and item.semantic_rank is not None:
            item.reasons.add("词法+语义")
    return merged


def _direct(item: Candidate, rank: int, mode: str) -> str:
    if mode == "precise":
        return "direct" if item.lexical_rank is not None and rank <= 20 else "explore"
    if item.lexical_rank is not None and rank <= 8:
        return "direct"
    if item.lexical_rank is not None and item.semantic_rank is not None and rank <= 16:
        return "direct"
    return "explore"


class HybridEngine:
    def __init__(self, index: SearchIndex, *, rrf_k: int = 60, model_id: str | None = None, lexical_limit: int = 200, semantic_limit: int = 200):
        self.index = index
        self.rrf_k = rrf_k
        self.model_id = model_id
        self.lexical_limit = lexical_limit
        self.semantic_limit = semantic_limit

    def search(self, query: str, *, language: str, corpora: tuple[str, ...], scopes: tuple[str, ...], resource_types: tuple[str, ...], mode: str, page_size: int, offset: int = 0) -> dict[str, Any]:
        lexical = self.index.lexical(query, language, corpora=corpora, scopes=scopes, resource_types=resource_types, limit=self.lexical_limit)
        semantic = self.index.semantic(query, language, corpora=corpora, scopes=scopes, resource_types=resource_types, limit=self.semantic_limit, model_id=self.model_id)
        merged = rrf_merge(lexical, semantic, k=self.rrf_k)
        ranked = sorted(merged.values(), key=lambda item: (-item.rerank_score, -(item.lexical_score or 0), item.locator))
        results = []
        for position, candidate in enumerate(ranked[offset : offset + page_size], offset + 1):
            record = self.index.get_record(candidate.locator)
            if not record:
                continue
            reasons = sorted(candidate.reasons or set())
            results.append({
                **record.to_dict(),
                "snippet": next((text for text in (record.text_zh, record.text_en, record.text_pali) if text), "")[:600],
                "lexical_score": round(candidate.lexical_score, 6),
                "semantic_score": round(candidate.semantic_score, 6),
                "rrf_score": round(candidate.rrf_score, 8),
                "rerank_score": round(candidate.rerank_score, 8),
                "match_reasons": reasons,
                "lane": _direct(candidate, position, mode),
            })
        return {
            "query": query,
            "language": language,
            "mode": mode,
            "total": len(ranked),
            "results": results,
            "semantic": {
                "enabled": bool(semantic),
                "degraded": not self.index.semantic_ready or not semantic,
                "reason": None if semantic else "semantic index or encoder unavailable",
                "index_version": self.index.manifest.get("version"),
            },
            "next_offset": offset + page_size if offset + page_size < len(ranked) else None,
        }


def build_engine(root: Path, *, model_id: str | None, dictionary_root: Path | None = None, rrf_k: int = 60, lexical_limit: int = 200, semantic_limit: int = 200) -> HybridEngine:
    return HybridEngine(SearchIndex(root, dictionary_root=dictionary_root), rrf_k=rrf_k, model_id=model_id, lexical_limit=lexical_limit, semantic_limit=semantic_limit)
