"""
CMR Specialist - Short Manual PDF (design specs, architecture, capabilities, UI guide).
Output: output/CMR_Specialist_Short_Manual.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

W, H = A4
OUT = "/Users/mac/Desktop/cmr_specialist/output/CMR_Specialist_Short_Manual.pdf"

TEAL = HexColor("#0F766E")
INK = HexColor("#1E293B")
MUTED = HexColor("#64748B")
LINE = HexColor("#CBD5E1")
CODE_BG = HexColor("#0F172A")
GREEN_BG = HexColor("#ECFDF5")
BLUE_BG = HexColor("#EFF6FF")
AMBER_BG = HexColor("#FFFBEB")

S_TITLE = ParagraphStyle("t", fontSize=22, leading=26, textColor=TEAL, alignment=TA_CENTER)
S_SUB = ParagraphStyle("s", fontSize=10, leading=14, textColor=MUTED, alignment=TA_CENTER)
S_H1 = ParagraphStyle("h1", fontSize=14, leading=17, textColor=TEAL, spaceBefore=12, spaceAfter=4)
S_H2 = ParagraphStyle("h2", fontSize=11, leading=14, textColor=INK, spaceBefore=8, spaceAfter=3)
S_B = ParagraphStyle("b", fontSize=9.2, leading=13, textColor=INK, spaceAfter=3)
S_BUL = ParagraphStyle("bul", parent=S_B, leftIndent=12, bulletIndent=4, spaceAfter=2)
S_CODE = ParagraphStyle("c", fontSize=8.2, leading=11, textColor=white)
S_CAP = ParagraphStyle("cap", fontSize=8, leading=10, textColor=MUTED, alignment=TA_CENTER)


def code_block(lines):
    rows = [[Paragraph(f"<font face='Courier'>{l}</font>", S_CODE)] for l in lines]
    t = Table(rows, colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                           ("ROUNDEDCORNERS", [3, 3, 3, 3]),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def badge_table(headers, rows):
    data = [[Paragraph(f"<b>{h}</b>", S_B) for h in headers]]
    for r in rows:
        data.append([Paragraph(c, S_B) for c in r])
    t = Table(data, colWidths=[55 * mm, 60 * mm, 55 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE_BG),
                           ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


story = []
A = story.append
A(Paragraph("CMR Specialist", S_TITLE))
A(Paragraph("Design Specs - Architecture - Capabilities - UI Guide (Short Manual, v2.0)", S_SUB))
A(HRFlowable(width="100%", thickness=1, color=LINE))

A(Paragraph("1. Design Principles", S_H1))
for b in [
    "<b>Store-first:</b> every input is persisted before any model call. No claim exists without a stored case, run, and step trail.",
    "<b>Model proposes, software enforces:</b> the model orders plans, extracts facts, drafts answers. The harness validates: allowlisted tools only, max 12 steps, patterned IDs regex-checked, approval gates, idempotency keys.",
    "<b>Graceful degradation:</b> model silence falls back to deterministic templates. Tasks keep moving; the fallback is flagged visibly (<i>plan_fallback</i>), never hidden.",
    "<b>Two tool systems:</b> internal tools (read/compute, unaudited) and the sealed tool module (soleDB writer, CHECK free / WRITE approval + audit).",
    "<b>Honest failure:</b> no evidence means the bounded fallback ('couldn't find supporting evidence'), never an invented answer.",
]:
    A(Paragraph(b, S_BUL, bulletText="\u2022"))

A(Paragraph("2. Architecture", S_H1))
A(Paragraph("Web API (port 8080) + background worker + SQLite/Postgres store + operator console + tool module over a mock CMR DB. Inference via OpenRouter (configurable). Config never auto-loads <i>.env</i>: web needs <i>--env-file .env</i>, worker needs env-exported variables.", S_B))
A(badge_table(["Layer", "Role", "Key files"],
    [["Intake", "Guard, intent (model-first + veto), extraction (model + regex floor)", "guard.py, intent.py, extractor.py"],
     ["Planning", "Model orders steps from allowlist; harness enforces; plan stored at creation", "planner.py, service.queue_task"],
     ["Execution", "Worker honors stored plan; policy gate; idempotent steps", "worker.py, service.execute_task"],
     ["Tool module", "CHECK/WRITE formulations; only DB writer; append-only audit", "tools/module.py, mockdb.py"],
     ["Knowledge", "Upload, chunk, publish; only <i>active</i> versions searchable", "knowledge APIs"]]))

A(Paragraph("3. Capabilities", S_H1))
A(Paragraph("Task families", S_H2))
for b in [
    "<b>payment_reconciliation</b> - needs RRR (12 digits) + date + account. Verifies receipt against ledger.",
    "<b>change_of_ownership</b> - needs plate + buyer + seller names. Names come from the model; plate is regex-validated.",
    "<b>general_support</b> - knowledge-grounded answers with cited spans.",
    "<b>Knowledge Q&amp;A</b> - answers cite published doc spans; empty base returns the bounded fallback.",
]:
    A(Paragraph(b, S_BUL, bulletText="\u2022"))
A(Paragraph("Task lifecycle", S_H2))
A(Paragraph("<i>queued</i> (all facts present) - <i>waiting_for_input</i> (missing facts + prompts; plan already stored) - <i>waiting_approval</i> (sensitive/WRITE steps) - <i>running - completed / failed</i>. Follow-up messages merge new facts and resume waiting tasks automatically.", S_B))
A(Paragraph("Visibility flags", S_H2))
for b in [
    "<b>plan_proposed_by:</b> <i>model</i> (reasoned) or <i>template</i> (fallback cover).",
    "<b>plan_fallback: true</b> means the template covered for a silent model - work continues, reasoning didn't happen. Clustered fallbacks signal quota/throttling, not code faults.",
]:
    A(Paragraph(b, S_BUL, bulletText="\u2022"))

A(Paragraph("4. UI Guide (http://localhost:8080)", S_H1))
A(badge_table(["Card", "What to do", "What you get back"],
    [["1 - New case", "Paste a question or task, Submit", "intent, task_id, status, missing facts + prompts, plan flags"],
     ["2 - Follow-up", "Case ID carries over; paste missing fact, Attach", "merged facts; waiting tasks resume (<i>resumed=1</i>)"],
     ["3 - Queue task", "Pick type + approval level, Queue", "direct task (use approval: always to see the gate)"],
     ["4 - Knowledge", "Upload file, then Publish the version id", "chunk count; only published versions are searchable"],
     ["Case state", "Refresh case / Refresh task", "fields, plan + <i>plan: model/template (fallback)</i> badge"],
     ["Approval", "Approve / Reject with reason", "waiting_approval tasks proceed or stop"]]))

A(Paragraph("5. Two guided exercises", S_H1))
A(Paragraph("Exercise A - waiting then resume (ownership). Card 1:", S_H2))
A(code_block(["Musa sold his car to Adaeze Okafor, please transfer the ownership"]))
A(Paragraph("Expect <i>waiting_for_input</i> + missing plate. Then Card 2:", S_B))
A(code_block(["the plate number is ABC123XY"]))
A(Paragraph("Expect resume, validation of the plate, then <i>completed</i>.", S_B))
A(Paragraph("Exercise B - straight-through (payment). Card 1:", S_H2))
A(code_block(["Please reconcile my Remita payment RRR 123456789012 made yesterday for account acct-X"]))
A(Paragraph("Expect <i>queued - completed</i>, receipt verified paid (RRR ...9012), cited knowledge spans.", S_B))

A(Paragraph("6. Troubleshooting", S_H1))
for b in [
    "Task stuck <i>queued</i>: worker down - restart it; check <i>/health oldest_queued_job_age_s</i>.",
    "Always <i>waiting_for_input</i>: Refresh case shows the missing fact + prompt - answer via Card 2.",
    "Fallback badges everywhere: model throttled - check server log for <i>[planner]/[extractor]</i> lines; wait, retry.",
    "Port busy on restart: kill stale processes first (<i>pkill -f harness.api.main</i>), then launch web + worker.",
    "Knowledge answers empty: document uploaded but not <i>published</i> - publish the version id.",
]:
    A(Paragraph(b, S_BUL, bulletText="\u2022"))

A(Spacer(1, 6 * mm))
A(Paragraph("Generated 2026-09-26 - CMR Specialist v2.0 (OpenRouter inference).", S_CAP))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                        topMargin=14 * mm, bottomMargin=14 * mm, title="CMR Specialist - Short Manual")
doc.build(story)
print("wrote", OUT)
