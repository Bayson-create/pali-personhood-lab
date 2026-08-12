"""Download a versioned private Blob prefix with the Container App identity."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


def sync_from_blob(url: str, destination: Path) -> int:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:  # pragma: no cover - Azure-only path
        raise RuntimeError("azure-identity and azure-storage-blob are required for INDEX_BLOB_URL") from exc
    parsed = urlparse(url.rstrip("/"))
    account_url = f"{parsed.scheme}://{parsed.netloc}"
    parts = parsed.path.strip("/").split("/", 1)
    if len(parts) != 2:
        raise ValueError("INDEX_BLOB_URL must be https://account/container/prefix")
    container, prefix = parts
    client = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
    container_client = client.get_container_client(container)
    destination.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for blob in container_client.list_blobs(name_starts_with=prefix.rstrip("/") + "/"):
        relative = blob.name[len(prefix.rstrip("/") + "/") :]
        if not relative:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            handle.write(container_client.download_blob(blob.name).readall())
        downloaded += 1
    if not (destination / "manifest.json").exists():
        raise RuntimeError("private Blob prefix did not contain manifest.json")
    return downloaded


def maybe_sync() -> None:
    url = os.getenv("INDEX_BLOB_URL")
    if url:
        count = sync_from_blob(url, Path(os.getenv("HYBRID_INDEX_DIR", "/app/index")))
        print(f"downloaded {count} immutable index blobs", flush=True)
