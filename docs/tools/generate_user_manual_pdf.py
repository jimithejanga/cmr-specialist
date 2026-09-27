"""
CMR Specialist — Full User & Operator Manual PDF.
Covers: capabilities, operator console UI (card by card), workflows,
tool module, API reference, task states, troubleshooting.
Output: output/CMR_Specialist_User_Manual.pdf
"""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

W, H = A4
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = str(ROOT / "docs" / "output" / "CMR_Specialist_User_Manual.pdf")

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
BLUE_BG = HexColor("#EFF6FF")
BLUE_LINE = HexColor("#3B82F6")


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
sFlow = ParagraphStyle("Flow", fontName="Helvetica-Bold", fontSize=8.4, leading=12, textColor=INK,
                       alignment=TA_CENTER)


def code_block(lines):
    if isinstance(lines, str):
        lines = lines.split("\n")
    paras = [Paragraph(esc(l) if l.strip() else "<br/>", sCode) for l in lines]
    t = Table([[p] for p in paras], colWidths=[170 * mm])
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
    bg, line = (GREEN_BG, GREEN_LINE) if kind == "tip" else (
        (AMBER_BG, AMBER_LINE) if kind == "warn" else (BLUE_BG, BLUE_LINE))
    label = {"tip": "NOTE", "warn": "WARNING", "info": "DESIGN RULE"}.get(kind, "NOTE")
    t = Table([[Paragraph(f"<b>{label}.</b>  {esc(text)}", sBody)]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 1, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def flow_row(steps):
    row = []
    for i, s in enumerate(steps):
        row.append(Paragraph(f"<b>{esc(s)}</b>", sFlow))
        if i < len(steps) - 1:
            row.append(Paragraph("<b>-&gt;</b>", ParagraphStyle(
                "arr", parent=sFlow, textColor=TEAL, fontSize=11)))
    widths = []
    for i in range(len(steps)):
        widths.append((170 - (len(steps) - 1) * 10) / len(steps) * mm)
        if i < len(steps) - 1:
            widths.append(10 * mm)
    t = Table([row], colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4),
             ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 7),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    for i in range(0, len(row), 2):
        style += [("BACKGROUND", (i, 0), (i, 0), BLUE_BG),
                  ("BOX", (i, 0), (i, 0), 1, BLUE_LINE),
                  ("ROUNDEDCORNERS", [4, 4, 4, 4])]
    t.setStyle(TableStyle(style))
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, H - 14 * mm, W, 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(15 * mm, H - 9 * mm, "CMR SPECIALIST  ·  User & Operator Manual  ·  v2.0")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - 15 * mm, H - 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


story = []
A = story.append

# ── Cover ────────────────────────────────────────────────────────────────────
A(Spacer(1, 28 * mm))
A(Paragraph("CMR SPECIALIST · v2.0", ParagraphStyle("brand", parent=sSub,
      fontName="Helvetica-Bold", fontSize=11, textColor=TEAL, spaceAfter=4)))
A(Paragraph("Full User &<br/>Operator Manual", sTitle))
A(Spacer(1, 4 * mm))
A(Paragraph("Every capability of the system, and a complete guide to the operator console — "
            "what each card does, what each button triggers, and how work flows from complaint "
            "to verified resolution.",
            ParagraphStyle("coversub", parent=sSub, fontSize=10.5, leading=15)))
A(Spacer(1, 8 * mm))
A(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8, spaceBefore=4))
A(data_table(["Item", "Detail"], [
    ["System", "Lean case-centered agent (spec v2.0) + sealed tool module (CHECK/WRITE over mock CMR DB)"],
    ["Console", "http://localhost:8080 - dark two-column screen, API key only"],
    ["API docs", "http://localhost:8080/docs — interactive docs for every endpoint"],
    ["Health", "http://localhost:8080/health — readiness, database, queue age, worker heartbeat"],
], widths=[28 * mm, 142 * mm]))
A(Spacer(1, 6 * mm))
A(callout("You need two processes running: the web server (console + API) and the worker (executes "
          "queued tasks). The console never executes work itself — it only submits, approves, and displays.",
          kind="info"))

# ── 1. Capabilities ──────────────────────────────────────────────────────────
A(Paragraph("1 &nbsp;·&nbsp; What the system can do", sH1))
A(Paragraph("Six capability groups. Everything below is live and tested (20 automated checks).", sBody))
A(data_table(["Capability", "What it means in practice"], [
    ["1 · Cases", "Open a case from free text; every message preserved verbatim; full state (messages, "
     "fields + revision counts, tasks, outputs, recent events) on one screen."],
    ["2 · Fact extraction", "NIN, phone, email, plate/chassis, Remita RRR, payment date, account, names — "
     "each with confidence, source message, and extraction run. Corrections create new versions; "
     "originals are never overwritten."],
    ["3 · Knowledge Q&A", "Upload procedure documents (txt/md/pdf) → auto-chunked versions → publish to "
     "activate. Questions answered only from active versions with citations; no evidence means a clear "
     "fallback, never a guess."],
    ["4 · Task automation", "Queue payment_reconciliation, change_of_ownership, or general_support tasks. "
     "Missing facts park the task with per-field prompts; follow-ups resume it automatically."],
    ["5 · Approvals", "Sensitive steps pause in waiting_approval. Approve or reject with a reason from the "
     "console; rejections record why and fail the task visibly."],
    ["6 · Tool module (CHECK/WRITE)", "8 read-only CHECK formulations (profile, NIN, vehicle, owner, buyer, "
     "receipt, certificate, portal health) and 7 WRITE formulations (token resend, transfer, payment "
     "confirm/link, certificate resend/renew/correct) fired only by the sealed module against the mock "
     "CMR DB — every firing validated, authorized, idempotent, and audit-logged."],
], widths=[34 * mm, 136 * mm]))
A(Paragraph("What it deliberately cannot do: touch the real CMR database (mock only, behind a conformance "
            "gate), send real notifications, read scanned images (no OCR yet), or claim an external event "
            "occurred without a verified tool result.", sBody))

# ── 2. Getting started ───────────────────────────────────────────────────────
A(Paragraph("2 &nbsp;·&nbsp; Getting started", sH1))
A(Paragraph("Start here", sH2))
A(code_block(["cd /Users/mac/Desktop/cmr_specialist",
              "cp .env.example .env        # set real HARNESS_API_KEY + TOOL_MODULE_TOKEN",
              "pip install -r requirements-dev.txt",
              "",
              "# Terminal 1 — web (console + API)",
              "python -m uvicorn harness.api.main:app --host 0.0.0.0 --port 8080",
              "# Terminal 2 — worker (executes queued tasks)",
              "python -m harness.worker.worker",
              "",
              "curl -s localhost:8080/health     # expect status ok, database connected"]))
A(Paragraph("First five minutes in the console", sH2))
for b in ["Paste your <b>API key</b> in the header box (default <b>cmr-secret-key-2026</b>) and press "
          "<b>Health</b> — the activity log should print the health JSON.",
          "In card <b>1</b>, type <i>How do I renew my CMR certificate?</i> and press <b>Submit work</b>. "
          "The case id fills in automatically; badges show the intent and extracted fields.",
          "In card <b>4</b>, upload a procedure text file, then press <b>Publish</b> for the returned "
          "version id. Ask the question again — the answer now carries citations.",
          "In card <b>3</b>, queue a <b>payment_reconciliation</b> task. If facts are missing it parks with "
          "prompts — answer them in card <b>2</b> and watch it resume and complete.",
          "Press <b>Refresh task</b> any time to poll; the worker picks up queued work within ~2 seconds."]:
    A(Paragraph(b, sBullet, bulletText="•"))

# ── 3. Console UI ────────────────────────────────────────────────────────────
A(Paragraph("3 &nbsp;·&nbsp; Operator console — screen guide", sH1))
A(Paragraph("Layout: dark two-column screen. <b>Left column</b> = actions (cards 1–4). <b>Right column</b> "
            "= state and control (case state, approval, activity log). The header holds the title, the API "
            "key box, and the Health button. On narrow screens the columns stack.", sBody))
A(Paragraph("Header", sH2))
A(data_table(["Element", "Does"], [
    ["Title (CMR Specialist…)", "Identifies the console and version."],
    ["API key box", "Sent as X-API-Key on every mutating request. Must match the server's HARNESS_API_KEY."],
    ["Health button", "GETs /health and prints status, version, database, queue age to the activity log."],
], widths=[40 * mm, 130 * mm]))
A(Paragraph("Card 1 · New case (question or task)", sH2))
A(data_table(["Element", "Does"], [
    ["Text box", "The complaint or question. Example knowledge: renewal steps. Example task: paid RRR text."],
    ["Case title (optional)", "Human label; defaults to the first 80 characters of the text."],
    ["Submit work", "POST /cases. Creates the case, classifies intent, extracts facts, and — for tasks — "
     "queues the first task. Auto-fills the case-id box and the task-id box if a task was created."],
    ["Reset", "Clears the local boxes and output pane only. Nothing is deleted server-side."],
], widths=[40 * mm, 130 * mm]))
A(Paragraph("Card 2 · Follow-up on case", sH2))
A(data_table(["Element", "Does"], [
    ["Case id box", "Which case the follow-up attaches to (auto-filled after Submit)."],
    ["Follow-up text box", "Extra facts or a new question on the same case."],
    ["Attach to case", "POST /cases/{id}/messages. Re-runs extraction (new revisions, never overwrites) and "
     "resumes any waiting_for_input task whose missing facts just arrived."],
], widths=[40 * mm, 130 * mm]))
A(Paragraph("Card 3 · Queue automation task", sH2))
A(data_table(["Element", "Does"], [
    ["Task type dropdown", "payment_reconciliation · change_of_ownership · general_support."],
    ["Approval dropdown", "never (auto-run) · sensitive (pause on sensitive steps) · always (pause before any write)."],
    ["Instructions box", "What to do; falls back to the card-1 text if left empty."],
    ["Queue task", "POST /cases/{id}/tasks. Returns the task id into the task-id box; use an idempotency key "
     "via API for safe retries."],
    ["Run worker once", "Informational only — the real worker runs server-side. Then poll with Refresh task."],
], widths=[40 * mm, 130 * mm]))
A(Paragraph("Card 4 · Knowledge base", sH2))
A(data_table(["Element", "Does"], [
    ["File picker + Upload", "POST /knowledge/documents (txt/md/pdf). Returns document + version ids and chunk "
     "count; the version id auto-fills the publish box."],
    ["Version id + Publish", "POST /knowledge/versions/{id}/publish. Activates the version for retrieval "
     "(archives siblings). Only active versions can ground answers."],
], widths=[40 * mm, 130 * mm]))
A(Paragraph("Case state card (right column)", sH2))
A(data_table(["Element", "Does"], [
    ["Badges line", "Live summary: case short-id, each extracted field with revision (phone v2), each task "
     "with status (payment_reconciliation: waiting_for_input)."],
    ["Output pane", "Full JSON of GET /cases/{id} or GET /tasks/{id}: messages, fields, plans, steps, "
     "approvals, results, error refs."],
    ["Refresh case / Refresh task", "Re-fetch and repaint. Poll Refresh task while a worker runs."],
    ["Task id box", "Which task Refresh task and the Approval card act on (auto-filled on queue)."],
], widths=[40 * mm, 130 * mm]))
A(Paragraph("Approval card", sH2))
A(Paragraph("Reason box (optional, required for meaningful rejects) plus <b>Approve</b> / <b>Reject</b> "
            "buttons → POST /tasks/{id}/approvals. Approve returns the task to queued for the worker; "
            "reject fails it with your reason recorded. The result is printed to the activity log and the "
            "task view refreshed.", sBody))
A(Paragraph("Activity log", sH2))
A(Paragraph("Append-only feed, newest first, timestamped: every action with its HTTP status "
            "(create-case 200, task 200 queued, approval 200 …, task refresh 200). Your first stop when "
            "anything looks wrong — it tells you exactly which call did what.", sBody))

# ── 4. Workflows ─────────────────────────────────────────────────────────────
A(Paragraph("4 &nbsp;·&nbsp; Workflows & task states", sH1))
A(Paragraph("Knowledge question", sH2))
A(flow_row(["Submit (card 1)", "Classify + extract", "Retrieve active chunks", "Cited answer or fallback"]))
A(Paragraph("Automation task", sH2))
A(flow_row(["Queue (card 3)", "Validate fields", "Plan + approve", "Worker executes", "Validate + close"]))
A(Paragraph("Task states you will see in badges and the output pane:", sH2))
A(data_table(["State", "Meaning", "Your action"], [
    ["queued", "Waiting for the worker (picked up within ~2s).", "Wait / Refresh task."],
    ["leased / running", "Worker owns it and is executing steps.", "Wait."],
    ["waiting_for_input", "Missing facts; prompts list exactly what is needed.", "Answer via card 2 follow-up."],
    ["waiting_approval", "Sensitive step needs a human.", "Approve / Reject in the Approval card."],
    ["completed", "Done; result + steps + citations stored.", "Review output."],
    ["failed", "Terminal error with error_ref; nothing was falsely claimed.", "Read error_ref; fix input; requeue."],
    ["dead_letter", "Retries exhausted.", "Operator/engineering review."],
], widths=[34 * mm, 72 * mm, 64 * mm]))
A(callout("Reposting a task with the same idempotency key (API) returns the existing task — safe retries, "
          "no duplicate side effects. A worker restart resumes from the last committed step.", kind="tip"))

# ── 5. Tool module ───────────────────────────────────────────────────────────
A(Paragraph("5 &nbsp;·&nbsp; Tool module (CHECK / WRITE)", sH1))
A(Paragraph("The sealed database-access layer. The console and API never touch data directly: CHECK "
            "formulations verify (profile, NIN, vehicle, owner, buyer, receipt, certificate, portal health); "
            "WRITE formulations mutate (token resend, transfer, payment confirm/link, certificate "
            "resend/renew/correct) — each gated by approval, idempotency key, and the check verdict that "
            "justified it. Every firing is audit-logged with masked PII; replays skip completed keys.",
            sBody))
A(Paragraph("In the console you meet the module indirectly: waiting_approval badges, evidence-backed "
            "results in the task view, and audit rows behind every step. Full design: "
            "output/CMR_Specialist_Tool_Module_Architecture.pdf.", sBody))

# ── 6. API ───────────────────────────────────────────────────────────────────
A(Paragraph("6 &nbsp;·&nbsp; API quick reference", sH1))
A(data_table(["Method + path", "Console equivalent"], [
    ["POST /cases {text, title?}", "Card 1 → Submit work"],
    ["POST /cases/{id}/messages {text}", "Card 2 → Attach to case"],
    ["POST /cases/{id}/tasks {task_type, instructions?, approval_required?}", "Card 3 → Queue task"],
    ["GET /cases/{id}", "Refresh case"],
    ["GET /tasks/{id}", "Refresh task (steps, approvals, result/error)"],
    ["POST /tasks/{id}/approvals {decision, reason?}", "Approval card buttons"],
    ["POST /knowledge/documents (file)", "Card 4 → Upload"],
    ["POST /knowledge/versions/{id}/publish", "Card 4 → Publish"],
    ["GET /knowledge/documents", "List documents + version statuses"],
    ["GET /health", "Header → Health"],
], widths=[80 * mm, 90 * mm], mono_col=0))
A(Paragraph("Mutating calls need header X-API-Key. Interactive docs with try-it-out: /docs.", sBody))

# ── 7. Troubleshooting ───────────────────────────────────────────────────────
A(Paragraph("7 &nbsp;·&nbsp; Troubleshooting & FAQ", sH1))
A(data_table(["Symptom", "Check", "Fix"], [
    ["Console actions fail (401/403)", "API key box matches server HARNESS_API_KEY?", "Correct the key; press Health."],
    ["Tasks sit in queued", "/health oldest_queued_job_age_s rising", "Start/restart the worker process."],
    ["waiting_for_input won't clear", "Task view → waiting_reason.missing", "Post exactly those facts in card 2."],
    ["waiting_approval stuck", "Task view → approvals list", "Approve or Reject with a reason."],
    ["Answers never cited", "Version published? (card 4)", "Publish the version; only active versions ground answers."],
    ["PDF upload rejected", ".pdf/.txt/.md only; text extractable?", "Scanned-image PDFs need OCR (not yet built)."],
    ["Duplicate tasks", "Same idempotency key reused?", "That is the protection working — one task, one id."],
    ["Port 8080 busy", "lsof -ti:8080", "Kill the holder, restart the web process."],
], widths=[44 * mm, 58 * mm, 68 * mm]))
A(Paragraph("FAQ", sH2))
for b in ["<b>Do I need the worker running?</b> Yes for anything beyond Q&A — tasks queue without it and "
          "execute when it starts. Nothing is lost; leases expire and are reclaimed.",
          "<b>Where is my data?</b> SQLite at data/cmr_cases.db locally (or Postgres via DATABASE_URL). "
          "Back it up before upgrades.",
          "<b>Can the agent invent an answer?</b> No — empty retrieval yields the bounded fallback, and "
          "external claims require verified tool results.",
          "<b>Who approved a write?</b> The task view lists every approval with approver, decision, reason, "
          "and time; the module audit log holds the matching data-side row."]:
    A(Paragraph(b, sBullet, bulletText="•"))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=20 * mm, bottomMargin=15 * mm,
                        title="CMR Specialist — Full User & Operator Manual",
                        author="CMR Specialist")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(f"Wrote {OUT}")
