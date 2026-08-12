#!/usr/bin/env python3
"""Build a reproducible V4 evidence/locator coverage report.

The script never invents a locator.  It records the exact search-service
records returned for a small, versioned concept query set and leaves claims
without a hit unresolved for human review.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow direct execution from the repository's scripts/ directory.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from search_service.hybrid_core import HybridEngine, SearchIndex

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True, help="search_service index directory")
    parser.add_argument("--output", type=Path, default=Path("research/PERSONHOOD_EVIDENCE_INDEX.json"))
    parser.add_argument("--registry", type=Path, default=Path("research/claim_registry.json"))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    index = SearchIndex(args.index)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    claims_source = registry.get("claims", [])
    engine = HybridEngine(index, model_id=None, lexical_limit=max(20, args.limit), semantic_limit=max(20, args.limit))
    claims = []
    for claim in claims_source:
        queries = []
        for language, query in claim["queries"].items():
            if not query:
                continue
            response = engine.search(query, language=language, corpora=("v4",), scopes=(), resource_types=("corpus",), mode="explore", page_size=args.limit)
            records = []
            for result in response.get("results", []):
                records.append({key: result.get(key) for key in ("locator", "work_id", "row_id", "paranum", "anchor", "source", "version", "source_url", "path")})
            queries.append({"language": language, "query": query, "result_count": len(records), "records": records})
        resolved_count = sum(item["result_count"] for item in queries)
        exact_uid_count = sum(1 for item in queries for record in item["records"] if claim.get("uid") and (record.get("work_id") == claim["uid"] or claim["uid"] in str(record.get("locator", ""))))
        claims.append({**claim, "queries": queries, "resolved_locator_count": resolved_count, "exact_uid_count": exact_uid_count})

    payload = {
        "schema_version": "personhood-evidence-index/0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "search_index": str(args.index.resolve()),
        "index_status": index.status(),
        "method": "HybridEngine.search; lexical results remain valid when semantic index/model is unavailable",
        "coverage_scope": registry.get("scope"),
        "claims": claims,
        "review_required": [claim["id"] for claim in claims if claim["resolved_locator_count"] == 0 or (claim.get("uid") and claim.get("exact_uid_count", 0) == 0)],
        "locator_rule": "Only copy fields from returned Record; null is preferable to an invented V4 locator.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "claims": len(claims), "review_required": payload["review_required"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
