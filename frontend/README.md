# Standalone frontend

Serve this directory with any static HTTP server. The lab has no dependency
on the source site's hash router or globals:

```powershell
python -m http.server 4173 --directory frontend
```

Use `http://localhost:4173/?api=http://localhost:8099` to point the UI at the
standalone API. When the API or evidence service is unavailable, the local
deterministic trace remains usable and the UI marks the evidence/AI state as
degraded instead of inventing confirmation.
