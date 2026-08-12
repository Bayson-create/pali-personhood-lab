# Graphify provenance

The source repositories were queried and incrementally graphed before extraction. The graph was used to identify the standalone boundary:

- Frontend: `docs/personhood/` plus its local schema, fixtures and evidence assets.
- Backend: `personhood/`, `/api/personhood/*`, evidence audit and the read-only hybrid-search adapters.
- Excluded: accounts, forums, translation workflows, unrelated API routers, corpus dumps, model weights and secrets.

Regenerate local graphs with the installed Graphify skill after source changes; do not commit raw corpus data solely to make the graph larger.
