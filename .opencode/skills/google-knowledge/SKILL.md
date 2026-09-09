---
name: google-knowledge
description: Work on Diaglob Google OAuth, Drive, Sheets, Docs, Knowledge Bases, source ingestion, synchronization, storage, and Bedrock Knowledge integration.
compatibility: opencode
metadata:
  project: diaglob
  scope: google-knowledge
---

## Mandatory first step

Read root `AGENTS.md` before modifying this domain. It contains authoritative service boundaries and explicit files that must not be modified for Knowledge service extraction work.

## Architecture boundaries from the repository

Business logic for Knowledge belongs in `backend/app/services/`; `backend/app/api/knowledge.py` must remain a thin HTTP layer.

Existing responsibilities include:

- `knowledge_bases.py`: KB lifecycle, scope validation, provisioning retry
- `knowledge_ingestion.py`: ingestion refresh and reindex triggers
- `knowledge_source_lifecycle.py`: source listing/upload/folder expansion/deletion/deactivation
- `knowledge_sources.py`: existing source helpers; do not turn into a god module
- `knowledge_provisioning.py`: provisioning engine; root rules say do not modify
- `drive_file_sources.py`: Drive file add/sync orchestration
- `google_sheet_sources.py`: Google Sheet add/sync orchestration

Provider/client modules stay outside services according to `AGENTS.md`.

## Integration invariants

- Preserve OAuth state validation and organization ownership.
- Request only scopes required by the feature.
- Do not log Google access/refresh tokens.
- Preserve source type, MIME, filename, size-limit, modified-detection, no-change sync, storage, cleanup, and ingestion semantics unless the task explicitly changes one of them.
- Preserve selected-store/tenant scope semantics for Knowledge Bases and sources.
- Keep provider failures distinguishable from local validation/domain failures.

## Tests

Patch service functions at `app.services.<module>.<function>` where root `AGENTS.md` requires it, not router internals.

Useful baseline commands from `AGENTS.md`:

```bash
cd backend && python -m pytest -q
cd backend && python -m pytest tests/test_bedrock_knowledge_base.py tests/test_google_sheets.py -q
cd backend && python -c "import app.main; print('OK')"
```
