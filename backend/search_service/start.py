"""Azure-aware process entrypoint for the standalone search container."""
from __future__ import annotations

import uvicorn

from .blob_bootstrap import maybe_sync


def main() -> None:
    maybe_sync()
    uvicorn.run("search_service.app:app", host="0.0.0.0", port=8080, workers=1)


if __name__ == "__main__":
    main()
