"""Fill integration-manifest hashes from the standalone release tree."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_tree(directory: Path) -> str:
    digest = hashlib.sha256()
    root = ROOT
    prefix = directory.relative_to(root).as_posix()
    try:
        names = subprocess.check_output(['git', 'ls-files', '--', prefix], cwd=root, text=True).splitlines()
        paths = [root / name for name in names if '__pycache__' not in Path(name).parts and Path(name).suffix != '.pyc']
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    for path in sorted(paths):
        digest.update(path.relative_to(directory).as_posix().encode())
        # GitHub Actions checks out text files with LF while Windows worktrees
        # may contain CRLF. Hash the canonical text representation so the
        # release manifest is portable across both environments.
        if path.suffix.lower() in {'.js', '.json', '.css', '.md', '.py', '.html'}:
            digest.update(path.read_text(encoding='utf-8').replace('\r\n', '\n').encode('utf-8'))
        else:
            digest.update(path.read_bytes())
    return digest.hexdigest()


manifest_path = ROOT / 'integration-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
manifest['front_end']['sha256'] = sha256_tree(ROOT / 'frontend' / 'personhood')
manifest['back_end']['sha256'] = sha256_tree(ROOT / 'backend' / 'personhood')
manifest['generated_at'] = datetime.now(timezone.utc).isoformat()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(manifest, ensure_ascii=False, indent=2))
