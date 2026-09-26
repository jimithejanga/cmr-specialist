# CMR Specialist

Lean case-centered automation agent (spec v2.0) + sealed tool module
(formulator & firer) over a mock CMR database. One codebase, two processes
(web + worker), one database.

## Quickstart (local)

```bash
cp .env.example .env            # then set real secrets
pip install -r requirements-dev.txt

# Terminal 1 — web
python -m uvicorn harness.api.main:app --host 0.0.0.0 --port 8080
# Terminal 2 — worker
python -m harness.worker.worker
```

Console: `http://localhost:8080` · API docs: `http://localhost:8080/docs` ·
Health: `http://localhost:8080/health`

## Tests

```bash
pytest tests/ -q                # expect 20 passed
```

`test_lean_spec.py` covers Stages 0–3 (case memory, cited knowledge, durable
tasks, approvals). `test_tool_module.py` covers the tool module (catalog,
firing pipeline, append-only audit, conformance gate).

## Docker

```bash
cd docker && docker compose up --build        # SQLite, zero external services
# Postgres staging: uncomment db, then
DATABASE_URL=postgresql+psycopg://cmr:cmr-secret@db:5432/cmr docker compose up --build
```

## Layout

| Path | Role |
|---|---|
| `harness/agent/` | Controlled harness: guard, intent, extract, retrieve, plan, policy, validate |
| `harness/api/` | REST: cases, messages, tasks, approvals, knowledge, health |
| `harness/store/` | Durable memory: 12 tables, versioned fields, job leasing |
| `harness/tools/` | Tool module: formulations, mock DB, firing pipeline, audit, conformance |
| `harness/worker/` | Durable job loop (lease → execute → retry → resume) |
| `harness/inference/` | Mock / HTTP LLM provider adapters |
| `configs/settings.py` | All config via env (see `.env.example`) |
| `frontend/` | Operator console (served at `/`) |
| `data/knowledge/`, `data/procedures/` | Retrieval source PDFs |
| `output/` | Design PDFs (implementation manual, tool module architecture) |
| `generate_*_pdf.py` | Regenerate the PDFs in `output/` |

## Production notes

- Set `DATABASE_URL` to managed Postgres + fresh `HARNESS_API_KEY` /
  `TOOL_MODULE_TOKEN` per environment. Never commit `.env`.
- Scale signal: `oldest_queued_job_age_s` on `/health`. One worker handles
  ~100 tasks/day with headroom; add workers only when queue age persists.
- Cutover gate: the real CMR backend must pass `harness/tools/conformance.py`
  identically to the mock before any citizen case touches it.
