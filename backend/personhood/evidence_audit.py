"""Three-source evidence audit for the Pali personhood claim registry.

The audit is deliberately conservative: a search hit is a candidate, while
``confirmed`` requires a V4 locator, an Early Buddhist segment and a
SuttaCentral text response for canonical claims with a UID. Later layers are
reported separately and never silently promoted to canonical evidence.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from search_service.hybrid_core import HybridEngine, SearchIndex


def _v4_check(engine: HybridEngine, claim: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for language, query in claim.get("queries", {}).items():
        if not query or language not in {"zh", "en", "pali"}:
            continue
        response = engine.search(query, language=language, corpora=("v4",), scopes=(), resource_types=("corpus",), mode="precise", page_size=10)
        for result in response.get("results", []):
            records.append({key: result.get(key) for key in ("locator", "work_id", "row_id", "paranum", "anchor", "source", "version", "source_url", "uid", "segment_id", "snippet")})
    uid = claim.get("uid")
    exact = [record for record in records if uid and (record.get("uid") == uid or record.get("work_id") == uid or uid in str(record.get("locator", "")))]
    return {"status": "confirmed" if exact else ("candidate" if records else "missing"), "result_count": len(records), "exact_uid_count": len(exact), "records": records[:12]}


async def _early_check(client: httpx.AsyncClient, claim: dict[str, Any]) -> dict[str, Any]:
    query = claim.get("queries", {}).get("pali") or claim.get("queries", {}).get("en") or claim.get("queries", {}).get("zh")
    if not query:
        return {"status": "not_applicable", "result_count": 0, "records": []}
    # The static Early-Buddhist site has no search API of its own. Reuse the
    # backend's exact port of its client-side BM25 engine, which returns
    # segment-level provenance and the SuttaCentral URL for each hit.
    try:
        # The standalone lab vendors only the read-only search adapter, not
        # the source backend's ``api/app`` package.  Keeping this import
        # local makes the auditor usable from an independent clone while the
        # original backend can still provide its own adapter when the sync
        # script is run there.
        try:
            from early_buddhist_search import search
        except ImportError:
            # Compatibility path for the source backend while it is still
            # hosting the thin integration layer.
            from app.gotama.early_buddhist_search import search
        # The Early-Buddhist English index covers the full Tipitaka and is
        # the appropriate cross-check for Pali terms; Chinese is a narrower
        # legacy translation index.
        lang = "en" if claim.get("queries", {}).get("pali") or claim.get("queries", {}).get("en") else "zh"
        payload = await asyncio.wait_for(search(query, lang=lang, limit=10), timeout=8)
        records = [{key: hit.get(key) for key in ("uid", "segment", "title", "text", "url", "score")} for hit in payload.get("results", [])]
        uid = claim.get("uid")
        exact = [record for record in records if uid and record.get("uid") == uid]
        return {"status": "confirmed" if exact else ("candidate" if records else "missing"), "result_count": len(records), "exact_uid_count": len(exact), "records": records}
    except Exception as exc:  # network/dependency state is explicit
        return {"status": "unavailable", "reason": type(exc).__name__, "result_count": 0, "records": [], "query": query}


async def _suttacentral_check(client: httpx.AsyncClient, claim: dict[str, Any]) -> dict[str, Any]:
    uid = claim.get("uid")
    if not uid:
        return {"status": "not_applicable", "result_count": 0, "records": []}
    url = f"https://suttacentral.net/api/bilarasuttas/{uid}/sujato"
    try:
        response = await client.get(url, timeout=8, follow_redirects=True)
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__, "result_count": 0, "records": [], "url": url}
    if response.status_code >= 400:
        return {"status": "unavailable", "reason": f"http:{response.status_code}", "result_count": 0, "records": [], "url": url}
    try:
        payload = response.json()
        text = json.dumps(payload, ensure_ascii=False)[:1200]
    except ValueError:
        text = response.text[:1200]
    return {"status": "confirmed", "result_count": 1, "records": [{"uid": uid, "url": url, "excerpt": text}]}


async def build_audit(index_root: Path, registry_path: Path, *, network: bool = True) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    index = SearchIndex(index_root)
    engine = HybridEngine(index, model_id=None, lexical_limit=30, semantic_limit=0)
    async with httpx.AsyncClient(headers={"User-Agent": "pali-personhood-audit/1.0"}) as client:
        async def audit_claim(claim: dict[str, Any]) -> dict[str, Any]:
            v4 = await asyncio.to_thread(_v4_check, engine, claim)
            if network:
                early, sc = await asyncio.gather(_early_check(client, claim), _suttacentral_check(client, claim))
            else:
                early = {"status": "not_run", "result_count": 0, "records": []}
                sc = {"status": "not_run", "result_count": 0, "records": []}
            if claim.get("layer") in {"canonical", "vinaya", "abhidhamma"} and claim.get("uid"):
                # A canonical release claim needs all three independent checks.
                # ``unavailable`` is never promoted to confirmation.
                status = "confirmed" if all(source["status"] == "confirmed" for source in (v4, early, sc)) else "review_required"
            elif v4["status"] == "confirmed":
                status = "candidate"
            else:
                status = "review_required"
            return {"id": claim["id"], "layer": claim["layer"], "uid": claim.get("uid"), "statement": claim["statement"], "status": status, "sources": {"v4": v4, "early_buddhist": early, "suttacentral": sc}}
        rows = list(await asyncio.gather(*(audit_claim(claim) for claim in registry["claims"])))
    return {
        "schema_version": "personhood-evidence-audit/1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": registry["registry_version"],
        "coverage_scope": registry["scope"],
        "network_checks": network,
        "index_status": index.status(),
        "claims": rows,
        "summary": {
            "total": len(rows),
            "confirmed": sum(row["status"] == "confirmed" for row in rows),
            "candidate": sum(row["status"] == "candidate" for row in rows),
            "review_required": sum(row["status"] == "review_required" for row in rows),
        },
        "release_rule": "Only confirmed canonical claims may be shown as confirmed; candidate and review_required remain visibly provisional.",
    }
