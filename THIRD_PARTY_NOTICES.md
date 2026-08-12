# Third-party notices

This repository contains project-owned integration code derived from the following user-controlled repositories. Their history is intentionally not copied into this standalone repository:

- `https://github.com/Bayson-create/Sutta-Study-Guide.git`
- `https://github.com/Bayson-create/sutta-study-guide-backend.git`
- `https://github.com/Bayson-create/Early-Buddhist.git` (source adapter only; no corpus is bundled)

External research and text sources are referenced by URL, version, commit and hash in `artifacts.lock.json`. No V4 text dump, Early-Buddhist corpus, SuttaCentral export, model weight or credential is included in the first release.

Review the upstream repository licenses and any future scholarly source license before redistributing downloaded artifacts.

The Python runtime dependencies in `backend/requirements.txt` (FastAPI,
httpx, Pydantic, Uvicorn and the OpenCC reimplementation) are not vendored;
their package metadata remains the license authority. A release environment
should run `pip install pip-licenses && pip-licenses --format=markdown` and
attach the output to its audit record before redistributing a built image.
