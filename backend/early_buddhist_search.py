"""Keyword (BM25) search over the Early-Buddhist project's segment-level
Pali Canon index (github.com/Bayson-create/Early-Buddhist), ported from its
docs/search_engine.js client-side engine.

Why a port instead of calling an API: that project is a static site with
no server-side search endpoint of its own - the engine only exists as
browser JS, reading static JSON index files. This reimplements the same
algorithm (BM25 k1=1.5/b=0.75, a Chinese vocabulary-driven longest-match
tokenizer with a character-bigram OOV fallback, and a proximity bonus)
against the SAME static index files, fetched on demand from the live
GitHub Pages deployment and cached in-process for the life of this
container - the same "only pull the shards/chunks a query actually
touches" design the JS engine uses, not a bulk download. The bucket
hashing (`zlib.crc32(word) % buckets`) is exactly the function
build_word_index.py used to build the index (Python stdlib zlib.crc32,
not a reimplementation), so no reindexing or local data copy is needed
and this stays in sync with whatever is actually deployed to the site.

Each hit is one Pali-Canon SEGMENT (one sentence/verse out of ~356K
across the whole Tipitaka - Sutta, Vinaya and Abhidhamma), not a whole
sutta - directly quotable, unlike a full-document fetch the model would
otherwise have to read through to find the relevant sentence in.
"""
from __future__ import annotations

import asyncio
import math
import re
import zlib
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx
from opencc import OpenCC

_BASE_URL = "https://bayson-create.github.io/Early-Buddhist"
_TIMEOUT = httpx.Timeout(connect=5, read=20, write=5, pool=5)

BM25_K1 = 1.5
BM25_B = 0.75
BIGRAM_FALLBACK_WEIGHT = 0.6
DEFAULT_LIMIT = 15

_t2s = OpenCC("t2s")
_s2t = OpenCC("s2t")

_EN_STOP = frozenset(
    "what is are the a an of in to and or how do does this that it for with on at by from as be was were "
    "been being have has had will would could should may might can shall not no but if then so than too "
    "very just about which who whom whose when where why i you he she we they me him her us them my your "
    "his its our their".split()
)
# Same particle list as build_word_index.py's ZH_STOP (minus glossary
# overlaps) - only ever discards near-zero-IDF grammatical filler.
_ZH_INDEX_STOP = frozenset(
    "的了是在与及之也而或则即乃矣焉哉故若如所其此彼吾汝你他她它們们着過过被把讓让給给對对從从到為为以於于"
    "又還还並并但卻却才就都很更最不沒没無无一個个這这那些"
)
_EN_TOKEN_RE = re.compile(r"[a-zA-Zāīūṁṃṅñṭḍṇḷ']+")
_DIACRITIC_FOLD = str.maketrans({
    "ā": "a", "ī": "i", "ū": "u", "ṁ": "m", "ṃ": "m", "ṅ": "n",
    "ñ": "n", "ṭ": "t", "ḍ": "d", "ṇ": "n", "ḷ": "l",
})


# ---------------------------------------------------------------------------
# On-demand fetch + in-process cache (mirrors `engineState` in search_engine.js)
# ---------------------------------------------------------------------------

_cache: dict[str, object] = {}


async def _fetch_json(client: httpx.AsyncClient, path: str):
    if path in _cache:
        return _cache[path]
    resp = await client.get(f"{_BASE_URL}/{path}")
    resp.raise_for_status()
    data = resp.json()
    _cache[path] = data
    return data


def _bucket_for(word: str, buckets: int) -> int:
    return zlib.crc32(word.encode("utf-8")) % buckets


async def _load_word_shard(client, lang: str, word: str, buckets: int) -> dict:
    b = _bucket_for(word, buckets)
    return await _fetch_json(client, f"word_index_{lang}/shard_{b:03d}.json")


async def _load_bigram_shard(client, bigram: str) -> dict:
    b = _bucket_for(bigram, 64)
    return await _fetch_json(client, f"bigram_index_zh/shard_{b:03d}.json")


async def _load_chunk(client, lang: str, chunk_idx: int) -> list[dict]:
    return await _fetch_json(client, f"search_index_{lang}_{chunk_idx}.json")


# ---------------------------------------------------------------------------
# Tokenizers (must match build_word_index.py's offline tokenization exactly)
# ---------------------------------------------------------------------------

def _zh_tokenize(text: str, vocab: set[str], vocab_max_len: int) -> tuple[list[str], list[str]]:
    """Vocabulary-driven greedy longest-match segmentation, ported from
    zhTokenizeQuery() in search_engine.js. Returns (words, oov_bigrams)."""
    # The public Early-Buddhist deployment has used both simplified and
    # traditional vocabulary snapshots.  Start with the site's simplified
    # query form, but accept a traditional vocabulary term at the same
    # character position so either snapshot remains searchable.
    norm = _t2s.convert(text.strip())
    traditional_norm = _s2t.convert(norm)
    traditional_terms = sum(1 for term in vocab if _t2s.convert(term) != term)
    simplified_terms = sum(1 for term in vocab if _s2t.convert(term) != term)
    oov_norm = traditional_norm if traditional_terms > simplified_terms else norm
    n = len(norm)
    covered = [False] * n
    words: list[str] = []
    i = 0
    while i < n:
        match_len = 0
        for length in range(min(vocab_max_len, n - i), 0, -1):
            candidate = norm[i:i + length]
            if candidate in vocab:
                match_len = length
                word = candidate
                break
            traditional_candidate = traditional_norm[i:i + length]
            if traditional_candidate in vocab:
                match_len = length
                word = traditional_candidate
                break
        if match_len:
            if word not in _ZH_INDEX_STOP:
                words.append(word)
            for k in range(i, i + match_len):
                covered[k] = True
            i += match_len
        else:
            i += 1

    oov_bigrams = {oov_norm[k:k + 2] for k in range(n - 1) if not covered[k] or not covered[k + 1]}
    return words, sorted(oov_bigrams)


def _en_tokenize(text: str) -> list[str]:
    words = []
    for m in _EN_TOKEN_RE.finditer(text.strip().lower()):
        w = m.group(0)
        if w in _EN_STOP or len(w) < 2:
            continue
        words.append(w)
    return words


# ---------------------------------------------------------------------------
# BM25 scoring
# ---------------------------------------------------------------------------

def _bm25_contribution(df: int, tf: int, entry_len: int, n: int, avgdl: float) -> float:
    idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
    tf_norm = (tf * (BM25_K1 + 1)) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * (entry_len / avgdl)))
    return idf * tf_norm


def _proximity_bonus(offsets: list[int]) -> float:
    if len(offsets) < 2:
        return 0.0
    ordered = sorted(offsets)
    span = ordered[-1] - ordered[0]
    return len(offsets) / (span + len(offsets))


@dataclass
class _ScoreRec:
    score: float = 0.0
    matched_words: set[str] = field(default_factory=set)
    offsets: list[int] = field(default_factory=list)


async def _score_words(
    client, words: list[str], lang: str, manifest: dict, lengths: list[int],
) -> dict[int, _ScoreRec]:
    n, avgdl, buckets = manifest["n_entries"], manifest["avgdl"], manifest["buckets"]
    scores: dict[int, _ScoreRec] = {}

    for word in words:
        shard = await _load_word_shard(client, lang, word, buckets)
        postings = shard.get(word)
        matched_word = word
        if postings is None and lang == "en":
            folded = word.translate(_DIACRITIC_FOLD)
            if folded != word:
                shard = await _load_word_shard(client, lang, folded, buckets)
                postings = shard.get(folded)
                matched_word = folded
        if postings is None:
            continue
        df = len(postings)
        for entry_id, tf, offsets in postings:
            contrib = _bm25_contribution(df, tf, lengths[entry_id], n, avgdl)
            rec = scores.setdefault(entry_id, _ScoreRec())
            rec.score += contrib
            rec.matched_words.add(matched_word)
            rec.offsets.append(offsets[0])
    return scores


async def _apply_bigram_fallback(client, oov_bigrams: list[str], scores: dict[int, _ScoreRec]) -> None:
    if not oov_bigrams:
        return
    weight = BIGRAM_FALLBACK_WEIGHT / len(oov_bigrams)
    for bg in oov_bigrams:
        shard = await _load_bigram_shard(client, bg)
        ids = shard.get(bg)
        if not ids:
            continue
        for entry_id in ids:
            rec = scores.setdefault(entry_id, _ScoreRec())
            rec.score += weight
            rec.matched_words.add(f"~{bg}")


def _apply_proximity(scores: dict[int, _ScoreRec]) -> None:
    for rec in scores.values():
        rec.score *= 1 + 0.5 * _proximity_bonus(rec.offsets)


def _filter_by_collection(
    scores: dict[int, _ScoreRec], entry_collections: dict, collection: str | None,
) -> dict[int, _ScoreRec]:
    if not collection:
        return scores
    keys = entry_collections["keys"]
    if collection not in keys:
        return {}
    idx = keys.index(collection)
    cmap = entry_collections["map"]
    return {eid: rec for eid, rec in scores.items() if cmap[eid] == idx}


async def _resolve_entries(client, ranked_ids: list[int], lang: str, chunk_size: int) -> dict[int, dict]:
    by_chunk: dict[int, list[int]] = {}
    for eid in ranked_ids:
        by_chunk.setdefault(eid // chunk_size, []).append(eid)

    chunks = await asyncio.gather(*(_load_chunk(client, lang, idx) for idx in by_chunk))
    resolved: dict[int, dict] = {}
    for (chunk_idx, ids), chunk in zip(by_chunk.items(), chunks):
        for eid in ids:
            resolved[eid] = chunk[eid % chunk_size]
    return resolved


def _reader_url(
    *, uid: str, segment: str, lang: str, query: str, collection: str, text: str,
    matched_words: list[str],
) -> str:
    """Build the Early Buddhist reader deep link for one exact hit.

    The reader accepts the same stable ``view/lang/coll/seg/anc`` parameters
    used by the site's own search UI.  Keeping this URL beside the tool
    result means a chat citation and a browsable hit use one locator instead
    of trying to infer a paragraph from a display-only snippet later.
    """
    params = {"view": uid, "lang": lang, "q": query}
    if collection:
        params["coll"] = collection
    if segment:
        params["seg"] = str(segment)
    if matched_words:
        params["mt"] = "|".join(matched_words)
    anchor = (text or "")[:180].replace("\n", " ").strip()
    if anchor:
        params["anc"] = anchor
    return f"{_BASE_URL}/?{urlencode(params)}"


def _result_from_entry(
    entry: dict, rec: _ScoreRec, lang: str, query: str, collections_meta: dict,
) -> dict:
    uid = entry["u"]
    collection_label = collections_meta.get(entry.get("c", ""), {}).get("collection", entry.get("c", ""))
    if lang == "en":
        segment, pali, text = entry.get("s", ""), entry.get("p", ""), entry.get("e", "")
        title = entry.get("t") or uid
    else:
        segment, pali = str(entry.get("i", "")), ""
        text = _t2s.convert(entry.get("z", ""))
        title = _t2s.convert(entry.get("t") or uid)
    matched_words = sorted(
        (word[1:] if word.startswith("~") else word)
        for word in rec.matched_words
        if word
    )
    # Normalize display terms to simplified Chinese so the chat hit list and
    # reader highlight the actual text regardless of the index snapshot's
    # vocabulary form.
    display_matched_words = [_t2s.convert(word) if lang == "zh" else word for word in matched_words]
    url = f"https://suttacentral.net/{uid}#{segment}" if segment else f"https://suttacentral.net/{uid}"
    return {
        "uid": uid,
        "segment": segment,
        "pali": pali,
        "text": text,
        "collection": collection_label,
        "authors": entry.get("a", []) if lang == "en" else [entry.get("a", "")],
        "url": url,
        "reader_url": _reader_url(
            uid=uid,
            segment=segment,
            lang=lang,
            query=query,
            collection=entry.get("c", ""),
            text=text,
            matched_words=display_matched_words,
        ),
        "title": f"{title} {segment}".strip(),
        "domain": "suttacentral.net",
        "snippet": (text or "")[:200],
        "anchor": (text or "")[:180].replace("\n", " ").strip(),
        "matched_words": display_matched_words,
        "score": round(rec.score, 3),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def search(
    query: str,
    lang: str = "zh",
    limit: int = DEFAULT_LIMIT,
    collection: str | None = None,
    offset: int = 0,
) -> dict:
    """Returns {"query", "lang", "results": [...], "error": str|None} - same
    never-raises contract as the other Gotama tools.

    Each result is one Pali-Canon segment, directly quotable (not a whole
    sutta the caller would need to read through): {uid, segment, pali,
    text, collection, authors, url, title, snippet, matched_words, score}.
    `url` points at suttacentral.net/{uid}; `reader_url` is a precise
    Early Buddhist reader deep link; the segment id is the precise
    locator within that page for the English (Bilara-aligned) index. The
    Chinese (legacy-HTML) index has no Bilara segment ids of its own, so
    `segment` there is the entry's running position within its sutta
    instead - still enough to tell the model roughly where in the sutta
    the quote sits, just not a URL-anchorable id.
    """
    lang = lang if lang in ("zh", "en") else "zh"
    query = (query or "").strip()
    limit = max(1, min(int(limit or DEFAULT_LIMIT), 40))
    offset = max(0, int(offset or 0))
    if not query:
        return {"query": query, "lang": lang, "results": [], "total": 0, "next_cursor": None, "error": "empty query"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            manifest, lengths, entry_collections, collections_meta = await asyncio.gather(
                _fetch_json(client, f"word_index_{lang}/manifest.json"),
                _fetch_json(client, f"word_index_{lang}/entry_lengths.json"),
                _fetch_json(client, f"word_index_{lang}/entry_collections.json"),
                _fetch_json(client, "collections.json"),
            )
            collections_meta = collections_meta.get("collections", {})

            if lang == "zh":
                vocab_list = await _fetch_json(client, "word_index_zh/vocab.json")
                vocab = set(vocab_list)
                vocab_max_len = len(vocab_list[0]) if vocab_list else 1
                words, oov_bigrams = _zh_tokenize(query, vocab, vocab_max_len)
            else:
                words, oov_bigrams = _en_tokenize(query), []

            if not words and not oov_bigrams:
                return {"query": query, "lang": lang, "results": [], "total": 0, "next_cursor": None, "error": None}

            scores = await _score_words(client, words, lang, manifest, lengths)
            if lang == "zh":
                await _apply_bigram_fallback(client, oov_bigrams, scores)
            _apply_proximity(scores)

            filtered = _filter_by_collection(scores, entry_collections, collection)
            ranked_all = sorted(filtered.items(), key=lambda kv: (-kv[1].score, kv[0]))
            total = len(ranked_all)
            ranked = ranked_all[offset:offset + limit]
            ranked_ids = [eid for eid, _ in ranked]

            entries = await _resolve_entries(client, ranked_ids, lang, manifest.get("chunk_size", 30000))
    except httpx.HTTPError as exc:
        return {
            "query": query,
            "lang": lang,
            "results": [],
            "total": 0,
            "next_cursor": None,
            "error": f"Early-Buddhist index fetch failed: {exc}",
        }

    results = []
    for eid, rec in ranked:
        entry = entries.get(eid)
        if not entry:
            continue
        results.append(_result_from_entry(entry, rec, lang, query, collections_meta))
    return {
        "query": query,
        "lang": lang,
        "offset": offset,
        "results": results,
        "total": total,
        "next_cursor": str(offset + limit) if offset + limit < total else None,
        "error": None,
    }
