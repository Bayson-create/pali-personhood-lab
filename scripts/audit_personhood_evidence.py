"""Run the conservative three-source evidence audit from a clean clone.

The script does not download a corpus or write credentials.  It reads the
configured V4 index and claim registry, then writes an auditable JSON snapshot.
Network checks are opt-in so CI can remain deterministic and offline.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-root", type=Path, required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("research/claim_registry.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/PERSONHOOD_EVIDENCE_AUDIT.json"),
    )
    parser.add_argument(
        "--network",
        action="store_true",
        help="also query Early-Buddhist and SuttaCentral; unavailable stays review_required",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from personhood.evidence_audit import build_audit

    result = asyncio.run(
        build_audit(
            args.index_root.resolve(),
            (repo_root / args.registry).resolve()
            if not args.registry.is_absolute()
            else args.registry.resolve(),
            network=args.network,
        )
    )
    output = (repo_root / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
