# Diaglob Architecture Rules

## Knowledge Domain Service Extraction

Business logic lives in `backend/app/services/`, not in API routers.
`backend/app/api/knowledge.py` must remain a thin HTTP layer:
- FastAPI dependencies and Pydantic serialization stay in the router
- Domain logic (DB queries, S3 operations, status transitions, error mapping) belongs in services
- HTTP handlers catch domain exceptions and translate them to HTTP status codes

### Service Modules

| Module | Responsibility |
|--------|---------------|
| `knowledge_bases.py` | KB CRUD lifecycle, scope validation, provisioning retry |
| `knowledge_ingestion.py` | Ingestion status refresh, source reindex triggers |
| `knowledge_source_lifecycle.py` | Source listing, upload, folder expansion, S3 deletion, deactivation |
| `knowledge_sources.py` | Existing source helpers (do NOT extend into god module) |
| `knowledge_provisioning.py` | Bedrock provisioning engine (do NOT modify) |
| `drive_file_sources.py` | Drive file add/sync orchestration |
| `google_sheet_sources.py` | Google Sheet add/sync orchestration |

### Rules

1. Never add business logic to `backend/app/api/` routers
2. Never move provider/client modules (`bedrock_ingestion.py`, `bedrock_knowledge_base.py`, `knowledge_storage.py`, `google_drive_client.py`, `google_sheets_client.py`) into services
3. Never modify `backend/app/models.py`
4. Never add routes directly in `backend/app/main.py`
5. Domain exceptions should be defined in the service that raises them
6. Tests patch at the service layer (`app.services.<module>.<function>`), not the router layer

## Useful Commands

```bash
# Run full backend test suite
cd backend && python -m pytest -q

# Run specific test files
cd backend && python -m pytest tests/test_bedrock_knowledge_base.py tests/test_google_sheets.py -q

# Import check
cd backend && python -c "import app.main; print('OK')"

# Route audit
cd backend && python -c "from app.main import app; routes=[r.path for r in app.routes if hasattr(r,'path')]; print(len(routes),'routes'); [print(r) for r in routes if 'knowledge' in r]"

# Frontend build
cd frontend && npm run build
```
