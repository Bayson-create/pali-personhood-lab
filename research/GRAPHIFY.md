# Graphify provenance

The source repositories were queried and incrementally graphed before extraction. The graph was used to identify the standalone boundary:

- Frontend: `docs/personhood/` plus its local schema, fixtures and evidence assets.
- Backend: `personhood/`, `/api/personhood/*`, evidence audit and the read-only hybrid-search adapters.
- Excluded: accounts, forums, translation workflows, unrelated API routers, corpus dumps, model weights and secrets.

Regenerate local graphs with the installed Graphify skill after source changes; do not commit raw corpus data solely to make the graph larger.

## 2026-08-13 incremental implementation audit

The interaction implementation keeps the graph boundary explicit:

- `frontend/personhood/lab.js` owns local session continuity, explicit user inputs and rendering only.
- `frontend/personhood/engine.js` remains the only JavaScript state-transition source.
- The integrated backend owns authenticated, explicitly requested case persistence; no guest run writes a case.
- The only cross-agent relationship is `observable-action-only`; no edge represents private mental state.

After the next release build, run Graphify incremental update on the standalone frontend and the integrated backend and fail review on an unreferenced evidence edge or a direct agent-to-agent internal-state relationship.
