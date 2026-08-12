# Standalone backend

Run from the repository root after installing `backend/requirements.txt`:

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
uvicorn backend.api:app --reload --port 8099
```

The API is deliberately stateless. `POST /api/personhood/episodes` returns a
deterministic trace, `GET /api/personhood/evidence` returns the checked-in
audit snapshot, and `POST /api/personhood/explain` only produces a bounded
local explanation of that trace. A future AI provider may explain evidence,
but may not create hidden psychological state or change the deterministic
engine output.
