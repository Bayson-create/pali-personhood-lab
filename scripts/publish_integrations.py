"""Publish only the standalone lab integration files into the two source repos."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob('*'):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--frontend-target', type=Path, required=True)
    parser.add_argument('--backend-target', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'integration-manifest.json').read_text(encoding='utf-8'))
    operations = [
        (root / 'frontend' / 'personhood', args.frontend_target / 'docs' / 'personhood'),
        (root / 'backend' / 'personhood', args.backend_target / 'personhood'),
        (root / 'backend' / 'api.py', args.backend_target / 'personhood_standalone_api.py'),
        (root / 'research' / 'PERSONHOOD_EVIDENCE_AUDIT.json', args.backend_target / 'docs' / 'PERSONHOOD_EVIDENCE_AUDIT.json'),
    ]
    if args.dry_run:
        for source, destination in operations:
            print(f'{source} -> {destination}')
        return
    for source, destination in operations:
        if source.is_dir():
            copy_tree(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    marker = {
        'source_of_truth': manifest['source_of_truth'],
        'release': manifest['release'],
        'integration_manifest': 'https://raw.githubusercontent.com/Bayson-create/pali-personhood-lab/main/integration-manifest.json',
        'policy': 'edit the standalone repository; regenerate these files for downstream repos',
    }
    for target in (args.frontend_target / 'docs' / 'personhood', args.backend_target / 'docs'):
        target.mkdir(parents=True, exist_ok=True)
        (target / 'PERSONHOOD_SOURCE_OF_TRUTH.json').write_text(json.dumps(marker, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
