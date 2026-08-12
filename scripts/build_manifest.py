"""Fill integration-manifest hashes from the standalone release tree."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_tree(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob('*') if p.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


manifest_path = ROOT / 'integration-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
manifest['front_end']['sha256'] = sha256_tree(ROOT / 'frontend' / 'personhood')
manifest['back_end']['sha256'] = sha256_tree(ROOT / 'backend' / 'personhood')
manifest['generated_at'] = datetime.now(timezone.utc).isoformat()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(manifest, ensure_ascii=False, indent=2))
