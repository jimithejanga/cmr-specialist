"""
CMR Specialist — Implementation & Hosting Manual PDF generator.
Covers: what was built, how it works, local run, testing, hosting, operations.
Output: output/CMR_Specialist_Implementation_Manual.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, HRFlowable, KeepTogether)

W, H = A4
OUT = "/Users/mac/Desktop/cmr_specialist/output/CMR_Specialist_Implementation_Manual.pdf"

TEAL = HexColor("#0F766E")
TEAL_DARK = HexColor("#134E4A")
INK = HexColor("#1E293B")
MUTED = HexColor("#64748B")
BG = HexColor("#F1F5F9")
CODE_BG = HexColor("#0F172A")
LINE = HexColor("#CBD5E1")
AMBER_BG = HexColor("#FFFBEB")
AMBER_LINE = HexColor("#F59E0B")
GREEN_BG = HexColor("#ECFDF5")
GREEN_LINE = HexColor("#10B981")


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


sTitle = ParagraphStyle("Title2", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=INK)
sSub = ParagraphStyle("Sub", fontName="Helvetica", fontSize=11, leading=15, textColor=MUTED)
sH1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=TEAL_DARK,
                     spaceBefore=14, spaceAfter=6)
sH2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=INK,
                     spaceBefore=10, spaceAfter=4)
sBody = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.2, leading=13.5, textColor=INK,
                       spaceAfter=5, alignment=TA_LEFT)
sBullet = ParagraphStyle("Bullet", parent=sBody, leftIndent=14, bulletIndent=4, spaceAfter=3)
sCode = ParagraphStyle("Code", fontName="Courier", fontSize=7.8, leading=11, textColor=white)
sCell = ParagraphStyle("Cell", fontName="Helvetica", fontSize=8.2, leading=11, textColor=INK)
sCellH = ParagraphStyle("CellH", parent=sCell, fontName="Helvetica-Bold", textColor=white)
sCellMono = ParagraphStyle("CellMono", parent=sCell, fontName="Courier", fontSize=7.6, leading=10)
sCaption = ParagraphStyle("Caption", fontName="Helvetica-Oblique", fontSize=8, leading=11,
                          textColor=MUTED, alignment=TA_CENTER, spaceAfter=8)
sFooter = ParagraphStyle("Footer", fontName="Helvetica", fontSize=7.5, textColor=white)


def code_block(lines):
    if isinstance(lines, str):
        lines = lines.split("\n")
    paras = [Paragraph(esc(l) if l.strip() else "<br/>", sCode) for l in lines]
    inner = [[p] for p in paras]
    t = Table(inner, colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def data_table(headers, rows, widths=None, mono_col=None):
    data = [[Paragraph(esc(h), sCellH) for h in headers]]
    for r in rows:
        row = []
        for i, c in enumerate(r):
            st = sCellMono if mono_col is not None and i == mono_col else sCell
            row.append(Paragraph(esc(str(c)), st))
        data.append(row)
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), TEAL_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), BG))
    t.setStyle(TableStyle(style))
    return t


def callout(text, kind="tip"):
    bg, line = (GREEN_BG, GREEN_LINE) if kind == "tip" else (AMBER_BG, AMBER_LINE)
    label = "NOTE" if kind == "tip" else "WARNING"
    inner = [[Paragraph(f"<b>{label}.</b>  {esc(text)}", sBody)]]
    t = Table(inner, colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 1, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, H - 14 * mm, W, 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(15 * mm, H - 9 * mm, "CMR SPECIALIST  ·  Implementation & Hosting Manual  ·  v2.0")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - 15 * mm, H - 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


story = []
A = story.append

# ── Cover ────────────────────────────────────────────────────────────────────
A(Spacer(1, 34 * mm))
A(Paragraph("CMR SPECIALIST", ParagraphStyle("brand", parent=sSub, fontName="Helvetica-Bold",
                                             fontSize=11, textColor=TEAL, spaceAfter=4)))
A(Paragraph("Implementation &<br/>Hosting Manual", sTitle))
A(Spacer(1, 4 * mm))
A(Paragraph("Lean case-centered agent (spec v2.0): what was built, how it runs, "
            "how to test it, and how to host it — from laptop to cloud.",
            ParagraphStyle("coversub", parent=sSub, fontSize=10.5, leading=15)))
A(Spacer(1, 8 * mm))
A(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8, spaceBefore=4))
A(data_table(["Item", "Detail"], [
    ["Scope", "Stages 0–3: foundation, case memory, knowledge retrieval, task agent + operator UI"],
    ["Stack", "FastAPI + SQLAlchemy + SQLite (local) / PostgreSQL (cloud) + background worker"],
    ["Entry points", "Web: harness.api.main  ·  Worker: harness.worker.worker"],
    ["Tests", "tests/test_lean_spec.py — 7 checks, all passing"],
], widths=[38 * mm, 132 * mm]))
A(Spacer(1, 6 * mm))
A(callout("Start with one real task type (payment_reconciliation) and prove it end to end "
          "before adding more tools, channels, or agents.", kind="tip"))

# ── 1. What was implemented ──────────────────────────────────────────────────
A(Paragraph("1 &nbsp;·&nbsp; What was implemented", sH1))
A(Paragraph("The codebase was rebuilt around one principle from the spec: <b>the case database "
            "is the memory</b>. Every input, extracted fact, run, tool call, citation, approval, "
            "and state change is a database row. The model proposes; typed schemas, policy checks, "
            "and deterministic code enforce.", sBody))
A(Paragraph("Module map", sH2))
A(data_table(["Module", "Responsibility"], [
    ["configs/settings.py", "Typed config (DATABASE_URL, API key, ports, worker/retrieval limits)"],
    ["harness/store/ (database, models, repository)", "11-table durable memory, versioned extraction, job leasing"],
    ["harness/agent/ (guard, intent, extractor, retriever, planner, policy, validator, service)",
     "Controlled harness: 5-way intent router, typed extraction, active-only retrieval, bounded plans"],
    ["harness/tools/registry.py", "6 allowlisted tools with timeout, retry, permission level"],
    ["harness/worker/worker.py", "Durable worker loop: lease, execute, retry, resume after restart"],
    ["harness/api/main.py + schemas.py", "Spec interfaces: cases, messages, tasks, approvals, knowledge, health"],
    ["frontend/index.html", "Operator console: submit work, follow-ups, tasks, approvals, knowledge upload"],
    ["docker/", "Web + worker containers; optional local Postgres service"],
    ["tests/test_lean_spec.py", "Exit checks for Stages 0–3"],
], widths=[62 * mm, 108 * mm]))
A(Paragraph("Table 1 — where each spec concern lives in code.", sCaption))
A(Paragraph("Data model (all rows carry case/task/run linkage for audit)", sH2))
A(data_table(["Table", "Key content"], [
    ["cases", "id, title, status, source channel, owner, timestamps"],
    ["case_inputs", "case_id, raw text (verbatim), sender, received time"],
    ["extracted_fields", "name, type, raw + normalized value, confidence, validation, version, accepted_by"],
    ["tasks", "case_id, task_type, status, plan, result, idempotency key, attempts, lease info"],
    ["agent_runs / run_steps", "intent, model, timings; per-step action, tool, args, result, retries"],
    ["knowledge_documents / versions / chunks", "file metadata + hash; version status; chunk text + locator"],
    ["citations", "run → document version → chunk + quoted span + score"],
    ["approvals", "task, requested action, requester/approver, decision, reason, times"],
    ["case_events", "append-only actor / event / state transition / payload history"],
], widths=[58 * mm, 112 * mm]))
A(Paragraph("How the seven spec rules are enforced", sH2))
A(data_table(["Rule", "Enforcement"], [
    ["Case memory first", "Nothing lives only in chat context; service.py persists input before any reasoning"],
    ["Extracted data is evidence", "New revision per correction (version+1); raw, normalized, source, run kept"],
    ["Retrieval before generation", "retriever.py queries active versions only; empty result → bounded fallback"],
    ["Harness controls model", "Pydantic schemas in agent/schemas.py accept or reject every proposal"],
    ["Tools allowlisted", "REGISTRY dict; unknown tool → not_allowlisted error, never executed"],
    ["Durable + idempotent jobs", "DB-backed lease; per-step idempotency keys skip already-done steps"],
    ["Scale after measurement", "/health exposes oldest-queued-job age; scale only when it persists"],
], widths=[42 * mm, 128 * mm]))

# ── 2. How it works ──────────────────────────────────────────────────────────
A(Paragraph("2 &nbsp;·&nbsp; How it works", sH1))
A(Paragraph("Knowledge question", sH2))
A(Paragraph("1. <b>Store input</b> — POST /cases persists the case and verbatim message first. "
            "2. <b>Classify</b> — intent router returns KNOWLEDGE_QUERY + confidence. "
            "3. <b>Extract</b> — entities (NIN, phone, RRR, plate…) stored as versioned fields. "
            "4. <b>Retrieve</b> — active knowledge versions only; chunk IDs recorded. "
            "5. <b>Generate + validate</b> — answer assembled from spans; citations required. "
            "Weak retrieval or failed validation returns the bounded no-evidence fallback instead of guessing.",
            sBody))
A(Paragraph("Automation task (one real type first: payment_reconciliation)", sH2))
A(Paragraph("1. <b>Store task</b> — POST /cases/{id}/tasks with idempotency key (reposts return the same task). "
            "2. <b>Validate fields</b> — required checklist is remita_rrr + payment_date + account_identifier; "
            "missing values park the task in <b>waiting_for_input</b> with per-field prompts. "
            "3. <b>Plan + policy</b> — plan stored before execution (validate_fields → knowledge_lookup → "
            "payment_status_check → draft_solution); sensitive tools pause in <b>waiting_approval</b>. "
            "4. <b>Worker executes</b> — each step stores arguments, result, status, retries. "
            "5. <b>Follow-up resumes</b> — new message re-runs extraction and flips waiting tasks back to queued.",
            sBody))
A(callout("The system never claims an external event occurred (payment confirmed, account updated, "
          "ownership transferred) unless a verified tool result or human approval proves it.",
          kind="warn"))

# ── 3. Run it locally ────────────────────────────────────────────────────────
A(Paragraph("3 &nbsp;·&nbsp; Run it locally (Stage 0)", sH1))
A(Paragraph("Prerequisites", sH2))
for b in ["<b>Python 3.10+</b> (3.11/3.12 verified) and <b>pip</b>.",
          "Core deps install with plain pip: <b>fastapi, uvicorn, pydantic, sqlalchemy, pypdf, requests, pyyaml</b> "
          "(heavy ML packages are optional and NOT required).",
          "Test client deps: <b>pytest, httpx</b>. Postgres driver <b>psycopg[binary]</b> only when using Postgres.",
          "Ports: web serves on <b>8080</b> by default (HARNESS_PORT). No other services needed for SQLite mode."]:
    A(Paragraph(b, sBullet, bulletText="•"))
A(Paragraph("Install", sH2))
A(code_block(["cd /Users/mac/Desktop/cmr_specialist",
              "pip install -r requirements.txt        # lean core (no torch/GPU needed)",
              "pip install pytest httpx pypdf         # tests + PDF knowledge ingestion"]))
A(Paragraph("Configure (all optional — defaults run out of the box)", sH2))
A(data_table(["Variable", "Default", "Purpose"], [
    ["DATABASE_URL", "sqlite:///.../data/cmr_cases.db", "System of record; point at Postgres for cloud"],
    ["HARNESS_API_KEY", "cmr-secret-key-2026", "Send as X-API-Key header (empty disables check in dev)"],
    ["HARNESS_PORT / HOST", "8080 / 0.0.0.0", "Web bind address"],
    ["HARNESS_DATA_DIR", "./data", "Local file area"],
    ["INFERENCE_PROVIDER", "mock", "mock | http (OpenAI-compatible endpoint)"],
    ["WORKER_POLL_INTERVAL_S", "2.0", "Queue poll cadence"],
], widths=[52 * mm, 58 * mm, 60 * mm], mono_col=0))
A(Paragraph("Start the two processes (two terminals, one codebase)", sH2))
A(code_block(["# Terminal 1 — web process",
              "uvicorn harness.api.main:app --host 0.0.0.0 --port 8080",
              "",
              "# Terminal 2 — worker process (same image, same DB)",
              "python -m harness.worker.worker",
              "",
              "# Health: expect database: connected",
              "curl localhost:8080/health"]))
A(Paragraph("Seed knowledge and ask a grounded question", sH2))
A(code_block(["# Upload a procedure text (PDF also accepted)",
              "curl -X POST localhost:8080/knowledge/documents \\",
              "  -F \"file=@renewal_steps.txt;type=text/plain\"",
              "# → {\"document_id\": ..., \"version_id\": \"<VER>\", \"chunks\": N}",
              "",
              "# Publish the version so retrieval can use it",
              "curl -X POST localhost:8080/knowledge/versions/<VER>/publish \\",
              "  -H 'Content-Type: application/json' -d '{}'",
              "",
              "# Ask — answer carries citations, or a clear fallback if no evidence",
              "curl -X POST localhost:8080/cases \\",
              "  -H 'Content-Type: application/json' -d '{\"text\":\"How do I renew my CMR certificate?\"}'"]))
A(Paragraph("Run a task end to end (payment reconciliation)", sH2))
A(code_block(["# 1. Submit (parks in waiting_for_input, tells you what is missing)",
              "curl -X POST localhost:8080/cases -H 'Content-Type: application/json' \\",
              "  -d '{\"text\":\"Reconcile my payment for account john@example.com\"}'",
              "# → {\"task_id\": \"<TASK>\", \"status\": \"waiting_for_input\", \"missing\": [\"remita_rrr\", ...]}",
              "",
              "# 2. Supply the missing facts on the same case",
              "curl -X POST localhost:8080/cases/<CASE>/messages -H 'Content-Type: application/json' \\",
              "  -d '{\"text\":\"My RRR is 123456789012, paid yesterday for account john@example.com\"}'",
              "",
              "# 3. Worker picks it up (or force one pass) and polls to completed",
              "curl localhost:8080/tasks/<TASK>   # steps, tool results, citations"]))
A(callout("Re-posting a task with the same idempotency_key returns the existing task — "
          "safe to retry clients and safe against double execution.", kind="tip"))

# ── 4. Testing ───────────────────────────────────────────────────────────────
A(Paragraph("4 &nbsp;·&nbsp; Testing (exit checks)", sH1))
A(Paragraph("Automated suite", sH2))
A(code_block(["python -m pytest tests/ -q",
              "# expected: 7 passed, 1 skipped",
              "# (tests/test_harness.py is a skipped pre-v2 prototype; the spec suite is test_lean_spec.py)"]))
A(data_table(["Test", "Stage", "What it proves"], [
    ["test_stage0_health", "0", "/health ok, version 2.0.0, database connected"],
    ["test_stage1_case_memory_versioned", "1", "Inputs preserved; phone correction → version 2, source + run kept"],
    ["test_stage2_knowledge_cited_or_fallback", "2", "Published chunks → cited answer; unrelated query → fallback"],
    ["test_stage3_task_async_idempotent_and_waiting", "3", "Missing RRR → waiting_for_input; worker completes; same key = same task"],
    ["test_stage3_approval_gate", "3", "approval:always → waiting_approval; approve → completes without gate-loop"],
    ["test_intent_enum_and_unsupported", "3", "5-way router incl. UNSUPPORTED + NEEDS_CLARIFICATION"],
    ["test_extractor_task_schema", "1–3", "Required-field checklist per task type incl. all-missing case"],
], widths=[62 * mm, 14 * mm, 94 * mm], mono_col=0))
A(Paragraph("Manual checklist before calling a stage done", sH2))
for b in ["Restart web + worker mid-task: the job is re-leased and continues from the last committed step.",
          "Post the same task twice with one idempotency key: one task row, no duplicate side effects.",
          "Ask with an empty knowledge base: bounded fallback, no invented procedure text.",
          "Request something out of policy (e.g. bypass verification): UNSUPPORTED refusal.",
          "Approve then reject paths: approved completes, rejected fails with the recorded reason.",
          "GET /cases/{id} shows messages, field revisions, tasks, and outputs without DB access."]:
    A(Paragraph(b, sBullet, bulletText="•"))

# ── 5. Hosting ───────────────────────────────────────────────────────────────
A(Paragraph("5 &nbsp;·&nbsp; Hosting", sH1))
A(Paragraph("Shape: one small web instance, one worker instance, one managed database. "
            "Keep it provider-neutral until budget and region are confirmed.", sBody))
A(Paragraph("Option A — single VPS with Docker Compose (simplest, staging-ready)", sH2))
A(code_block(["cd docker",
              "# default runs on SQLite inside a volume — zero external services",
              "docker compose up --build",
              "# web → http://<host>:8080  (health: /health, console: /)",
              "#",
              "# Staging with local Postgres: uncomment the db service in",
              "# docker/docker-compose.yml, then:",
              "DATABASE_URL=postgresql+psycopg://cmr:cmr-secret@db:5432/cmr docker compose up --build"]))
A(Paragraph("Option B — managed platform (Render / Railway / Fly / VPS + managed Postgres)", sH2))
for b in ["Create a <b>managed PostgreSQL</b> database (Neon, Supabase, RDS, or your platform's Postgres).",
          "Deploy <b>two services from the same image/commit</b>: web (<tt>uvicorn harness.api.main:app --host 0.0.0.0 --port 8080</tt>) "
          "and worker (<tt>python -m harness.worker.worker</tt>).",
          "Set <b>DATABASE_URL=postgresql+psycopg://user:pass@host:5432/cmr</b> plus HARNESS_API_KEY on both services; "
          "install <b>psycopg[binary]</b> in the image for Postgres.",
          "Point a health check at <b>GET /health</b>; alert when <b>oldest_queued_job_age_s</b> exceeds your target.",
          "Start with 1 web + 1 worker (concurrency 1–4). Scale only when queue age, provider limits, CPU, or DB latency persist."]:
    A(Paragraph(b, sBullet, bulletText="•"))
A(Paragraph("Production env (set on both web and worker)", sH2))
A(data_table(["Variable", "Example", "Notes"], [
    ["DATABASE_URL", "postgresql+psycopg://…@…:5432/cmr", "Managed Postgres; automated backups on"],
    ["HARNESS_API_KEY", "(long random secret)", "Staff/clients send as X-API-Key"],
    ["INFERENCE_PROVIDER", "mock (or http)", "http needs INFERENCE_HTTP_URL + key"],
    ["WORKER_POLL_INTERVAL_S", "2.0", "Lower only if queue age demands it"],
], widths=[52 * mm, 58 * mm, 60 * mm], mono_col=0))
A(callout("First deploy proves one workflow end to end: upload + publish knowledge, ask a cited "
          "question, run one payment_reconciliation task, approve it, then snapshot/restore the "
          "database and confirm history and queued work survive.", kind="tip"))

# ── 6. Operations ────────────────────────────────────────────────────────────
A(Paragraph("6 &nbsp;·&nbsp; Operations & troubleshooting", sH1))
A(data_table(["Symptom", "Check", "Fix"], [
    ["/health shows database: error", "DATABASE_URL, DB reachable, credentials", "Fix URL; restart both processes"],
    ["Tasks stuck in queued", "oldest_queued_job_age_s rising; worker logs", "Start/restart worker; raise concurrency to 2–4"],
    ["Task in waiting_for_input", "GET /tasks/{id} → waiting_reason.missing", "POST the missing facts to /cases/{id}/messages"],
    ["Task in waiting_approval", "GET /tasks/{id} → approvals", "POST /tasks/{id}/approvals approved/rejected"],
    ["Cited answer never appears", "version status must be active", "POST /knowledge/versions/{id}/publish"],
    ["PDF upload rejected", "pypdf installed; text extractable", "pip install pypdf; use text PDF, not scanned images"],
    ["Duplicate tasks", "idempotency_key on create", "Reuse keys; reposts return the same task id"],
], widths=[48 * mm, 62 * mm, 60 * mm]))
A(Paragraph("Security & privacy baseline (launch hardening, Stage 5)", sH2))
for b in ["Secrets via environment, never in code; least-privilege DB and tool credentials; staff auth at the edge.",
          "PII masking in logs; field-level access rules; retention categories; deliberate deletion workflow.",
          "File validation on upload; HTTPS termination; automated DB backups with a tested restore.",
          "Structured logs carry request/case/task/run IDs; track LLM latency, tokens, cost, failure category."]:
    A(Paragraph(b, sBullet, bulletText="•"))

# ── Appendix ─────────────────────────────────────────────────────────────────
A(Paragraph("Appendix A &nbsp;·&nbsp; API reference", sH1))
A(data_table(["Method & path", "Purpose"], [
    ["POST /cases", "Create case from text (+ optional title/sender/owner); runs intake"],
    ["POST /cases/{id}/messages", "Follow-up: attach info, re-extract, resume waiting tasks"],
    ["POST /cases/{id}/tasks", "Queue automation task (task_type, instructions, approval_required)"],
    ["GET /cases/{id}", "Case state: messages, versioned fields, tasks, outputs, recent events"],
    ["GET /tasks/{id}", "Progress: status, waiting reason, plan, steps, approvals, result/error"],
    ["POST /tasks/{id}/approvals", "Approve or reject a guarded action {decision, approver, reason}"],
    ["POST /knowledge/documents", "Upload source (txt/md/pdf) → chunked version (ready)"],
    ["POST /knowledge/versions/{id}/publish", "Activate version for retrieval (archives siblings)"],
    ["GET /knowledge/documents", "List documents + version statuses"],
    ["GET /health", "Readiness, DB, oldest queued-job age, worker heartbeat"],
], widths=[62 * mm, 108 * mm], mono_col=0))
A(Paragraph("Appendix B &nbsp;·&nbsp; Task lifecycle", sH2))
A(Paragraph("<b>queued → leased → running → completed</b>, with side exits to "
            "<b>waiting_for_input</b> (missing facts), <b>waiting_approval</b> (sensitive step), "
            "<b>failed</b> (terminal error + error_ref), and <b>dead_letter</b> (retries exhausted). "
            "Expired leases are reclaimed by the next worker.", sBody))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=20 * mm, bottomMargin=15 * mm,
                        title="CMR Specialist — Implementation & Hosting Manual",
                        author="CMR Specialist")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(f"Wrote {OUT}")
