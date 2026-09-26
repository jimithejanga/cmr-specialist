"""
CMR Specialist — Tool Module Architecture PDF (v3, final redesign).
The module is a FORMULATOR-and-FIRER: a catalog of pre-built CHECK / WRITE API
call formulations, and the sole executor against the (mock) database.
The harness is SELECTOR-and-FILLER: reasons, picks a formulation, fills it.
Output: output/CMR_Specialist_Tool_Module_Architecture.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

W, H = A4
OUT = "/Users/mac/Desktop/cmr_specialist/output/CMR_Specialist_Tool_Module_Architecture.pdf"

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
    canvas.drawString(15 * mm, H - 9 * mm, "CMR SPECIALIST  ·  Tool Module (Formulator)  ·  Phase 2 v3")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - 15 * mm, H - 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


story = []
A = story.append

# ── Cover ────────────────────────────────────────────────────────────────────
A(Spacer(1, 26 * mm))
A(Paragraph("CMR SPECIALIST · PHASE 2 (v3)", ParagraphStyle("brand", parent=sSub,
      fontName="Helvetica-Bold", fontSize=11, textColor=TEAL, spaceAfter=4)))
A(Paragraph("The Tool Module:<br/>Formulator & Firer", sTitle))
A(Spacer(1, 4 * mm))
A(Paragraph("A sealed database-access layer for the CMR Specialist. The module formulates and fires "
            "every database call; the harness selects and fills. Two verbs only — CHECK for verification, "
            "WRITE for direct database writes — against a mock database the harness and LLM cannot touch.",
            ParagraphStyle("coversub", parent=sSub, fontSize=10.5, leading=15)))
A(Spacer(1, 8 * mm))
A(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8, spaceBefore=4))
A(data_table(["Item", "Detail"], [
    ["Module role", "FORMULATOR + FIRER — owns the catalog of call templates; sole executor against the DB"],
    ["Harness role", "SELECTOR + FILLER — reasons over complaints, picks a formulation, fills it with case facts"],
    ["Verbs", "CHECK (verification tasks) · WRITE (direct DB writes). Nothing else exists."],
    ["Target", "Mock CMR database today; real CMR database tomorrow — same contracts, zero harness changes"],
    ["Memory", "Module owns an independent audit log; case history stays in the case DB"],
], widths=[28 * mm, 142 * mm]))
A(Spacer(1, 6 * mm))
A(callout("If a call is not formulated in the catalog, it cannot be made. There is no such thing as an "
          "off-catalog database action.", kind="info"))

# ── 1. Core idea ─────────────────────────────────────────────────────────────
A(Paragraph("1 &nbsp;·&nbsp; The core idea: a sealed doorway", sH1))
A(Paragraph("The harness and the LLM hold <b>no database credentials and no connection strings</b> — not "
            "to the mock, not to anything. The tool module holds them all. Data can only be reached through "
            "the module's formulated API calls, and every call is validated, authorized, executed, and logged "
            "by the module itself.", sBody))
A(flow_row(["Complaint on case", "Harness selects + fills formulation", "Module validates + fires",
            "Mock DB answers", "Module audits", "Verified resolution"]))
A(Spacer(1, 2 * mm))
A(Paragraph("Figure 1 — the only path to data. The harness never crosses the doorway; the module never "
            "reasons about complaints.", sCaption))
A(Paragraph("Division of labour, fixed permanently:", sH2))
A(data_table(["", "Module (formulator + firer)", "Harness (selector + filler)"], [
    ["Owns", "Catalog templates, credentials, connections, audit log",
     "Complaint reasoning, formulation choice, case facts"],
    ["Does", "Validate filled forms, fire calls, enforce approvals + idempotency, log everything",
     "Pick formulation, fill blanks, present approvals, assemble cited answers"],
    ["Never", "Reasons about complaints, invents calls, self-authorizes writes",
     "Fires calls, holds DB credentials, touches the DB directly"],
], widths=[18 * mm, 76 * mm, 76 * mm]))

# ── 2. Two verbs ─────────────────────────────────────────────────────────────
A(Paragraph("2 &nbsp;·&nbsp; Two verbs: CHECK and WRITE", sH1))
A(Paragraph("<b>CHECK</b> is for verification tasks. It looks at the database and answers — both plain "
            "lookups (<i>does this profile exist?</i>) and verdicts (<i>does this NIN match? is this payment "
            "on the right account?</i>). Verdicts live <i>inside</i> check results as a citable field, not as "
            "a separate operation. Checks are read-only, freely callable, never approved.", sBody))
A(Paragraph("<b>WRITE</b> writes directly to the database. Creates, updates, links, resends. Every write "
            "carries three attachments: a human approval, an idempotency key, and — where applicable — the "
            "evidence ref of the check that justified it. No exceptions, no self-authorization.", sBody))
A(data_table(["", "CHECK", "WRITE"], [
    ["Purpose", "Verification tasks: look up + judge", "Direct DB writes: create / update / link / resend"],
    ["Side effects", "None, ever", "Always; each one named and logged"],
    ["Approval", "Never needed", "Always required (single; dual for flag-class writes if added)"],
    ["Idempotency", "Not required (safe to repeat)", "Mandatory key; repeats are ignored, never re-applied"],
    ["Failure mode", "Returns not-found / unverifiable", "Returns error_ref; never claims success"],
], widths=[28 * mm, 71 * mm, 71 * mm]))
A(callout("Adding a capability means adding one formulation to the catalog — endpoint, schema, permission, "
          "approval, idempotency — with zero changes to harness code. The catalog is the only file that grows.",
          kind="tip"))

# ── 3. Formulation anatomy ───────────────────────────────────────────────────
A(Paragraph("3 &nbsp;·&nbsp; Anatomy of a formulation", sH1))
A(Paragraph("Every template in the catalog — check or write — is specified with exactly these fields. "
            "The formulation <i>is</i> the policy: read one template and you know everything about how that "
            "call behaves.", sBody))
A(code_block(['CHECK.receipt.lookup:',
              '  verb:        CHECK',
              '  endpoint:    GET /tool/check/receipt        (module API, not the DB)',
              '  inputs:      { remita_rrr: string(12-digit, required) }',
              '  permission:  standard      approval: none',
              '  idempotency: not-required  timeout: 15s     retries: 2 (reads only)',
              '  returns:     { status, amount, date, linked_account, verdict }']))
A(Spacer(1, 2 * mm))
A(code_block(['WRITE.payment.link:',
              '  verb:        WRITE',
              '  endpoint:    POST /tool/write/payment-link',
              '  inputs:      { remita_rrr: required, account_identifier: required }',
              '  permission:  sensitive    approval: single-operator',
              '  idempotency: required      timeout: 60s     retries: 0 (never blind-retry a write)',
              '  evidence:    requires CHECK.receipt.lookup verdict=paid on same run',
              '  returns:     { link_ref, status }  or  { error_ref }']))
A(Paragraph("Note the last line of the write template: a write formulation <i>names the check verdict it "
            "depends on</i>. Verify-before-write is therefore not a guideline — it is a field the firing "
            "pipeline enforces.", sBody))

# ── 4. CHECK catalog ─────────────────────────────────────────────────────────
A(Paragraph("4 &nbsp;·&nbsp; CHECK catalog (verification tasks)", sH1))
A(data_table(["Formulation", "Answers question", "Key inputs → verdict"], [
    ["CHECK.profile.lookup", "Does this applicant have a profile? (J1 OTP)", "phone/email → exists, username type"],
    ["CHECK.nin.verify", "Does the NIN match / is it valid? (J2)", "NIN → match / mismatch / suspended"],
    ["CHECK.nimc.health", "Is the NIMC portal actually down? (J2)", "— → up / degraded / down (sole downtime source)"],
    ["CHECK.vehicle.lookup", "What is on record for this vehicle? (J3–J5)", "plate/chassis → record, cert state"],
    ["CHECK.owner.lookup", "Who legally owns it? (J3)", "vehicle → owner + history count"],
    ["CHECK.buyer.search", "Is the buyer known? (J3)", "phone/email/NIN/TIN → profile match"],
    ["CHECK.receipt.lookup", "What is this payment's state? (J4)", "RRR → status, amount, date, linked account"],
    ["CHECK.certificate.lookup", "What is this certificate's state? (J5)", "plate → processing/approved/expired, age"],
], widths=[44 * mm, 62 * mm, 64 * mm], mono_col=0))
A(Paragraph("DND-status diagnosis (text ALLOW / STATUS to 2442) and the password-reset walkthrough stay "
            "grounded knowledge answers — no database is involved, so no formulation exists for them. OCR of "
            "receipt photos and transfer documents is an <i>upstream</i> helper (it reads images, not the DB) "
            "whose output feeds check inputs.", sBody))

# ── 5. WRITE catalog ─────────────────────────────────────────────────────────
A(Paragraph("5 &nbsp;·&nbsp; WRITE catalog (direct DB writes)", sH1))
A(data_table(["Formulation", "Writes what (to mock now, CMR later)", "Gate"], [
    ["WRITE.token.resend", "Password-reset token via phone/email (J1)", "Single approval"],
    ["WRITE.transfer.initiate", "Ownership transfer, seller-initiated (J3)", "Single approval; seller-only rule"],
    ["WRITE.payment.confirm", "Confirm-payment action on a request (J4)", "Single approval"],
    ["WRITE.payment.link", "Link RRR to correct account (J4)", "Single approval + receipt=paid evidence"],
    ["WRITE.certificate.resend", "Re-send certificate to email (J5)", "Single approval"],
    ["WRITE.certificate.renew", "Renew expired certificate (J5)", "Single approval + paid-RRR evidence"],
    ["WRITE.certificate.correct", "Field correction with reason (J5)", "Single approval + window rule + value allowlist"],
], widths=[44 * mm, 66 * mm, 60 * mm], mono_col=0))
A(Paragraph("Out of the catalog by design: stolen-flag unflagging (SOP investigation chain stays human), "
            "bank-side reversals (guidance + escalation only), and notifications (downstream sender, not a DB "
            "operation). The doorway stays a doorway.", sBody))
A(callout("Open NPF item carried forward: call-centre scripts allow certificate changes up to 3 months, the "
          "SOP refers post-30-day corrections to HQ. WRITE.certificate.correct ships with the stricter 30-day "
          "default until ruled.", kind="warn"))

# ── 6. Firing pipeline ───────────────────────────────────────────────────────
A(Paragraph("6 &nbsp;·&nbsp; The firing pipeline (inside the module)", sH1))
A(flow_row(["Filled form arrives", "Validate vs template", "Approval check", "Fire once", "Audit log row"]))
A(Spacer(1, 2 * mm))
A(Paragraph("Figure 2 — every call passes all five stages. A failure at any stage stops the call and is "
            "itself logged.", sCaption))
A(data_table(["Stage", "What happens", "On failure"], [
    ["1 · Validate", "Form matched to catalog template; types, required fields, value rules checked",
     "Rejected with field-level reason; harness asked to refill"],
    ["2 · Authorize", "CHECK: pass. WRITE: valid approval present? evidence ref present and fresh?",
     "WRITE parks in pending_approval; missing evidence → refused with reason"],
    ["3 · Fire", "Single DB execution via the repository; writes never auto-retried",
     "Transient error → bounded retry (reads) or terminal error_ref (writes)"],
    ["4 · Respond", "Typed envelope: {status, data, evidence_refs} or {status: failed, error_ref}",
     "Envelope always well-formed — callers never parse raw DB errors"],
    ["5 · Audit", "Row appended to module audit log (next section) before the response returns",
     "If the audit write fails, the call is treated as failed — no silent actions"],
], widths=[24 * mm, 82 * mm, 64 * mm]))

# ── 7. Audit ─────────────────────────────────────────────────────────────────
A(Paragraph("7 &nbsp;·&nbsp; The module's own audit system", sH1))
A(Paragraph("Two logs exist because two different questions get asked. The <b>case log</b> (harness side) "
            "answers <i>what did the agent do for this citizen?</i> The <b>module audit log</b> answers "
            "<i>what happened to the data?</i> When the two disagree, the module log is ground truth — which "
            "is exactly why it must belong to the module, not the harness.", sBody))
A(data_table(["Audit field", "Recorded", "Why"], [
    ["audit_id / timestamp", "UUID + UTC time", "Ordering and tamper-evident sequence"],
    ["formulation_id + verb", "e.g. WRITE.payment.link", "Which template fired"],
    ["caller ref", "Harness run_id + case_id", "Joins module truth to case story"],
    ["arguments (PII-masked)", "NIN/RRR last-4 only", "Audit without leaking identity data"],
    ["result summary", "Status + refs (link_ref, verdict)", "What changed / was found"],
    ["evidence refs", "Check verdict IDs cited", "Proves verify-before-write after the fact"],
    ["approval ref", "Approver + time (writes)", "Who authorized the mutation"],
    ["latency + error", "ms + error_ref if failed", "Performance and failure analysis"],
], widths=[44 * mm, 58 * mm, 68 * mm], mono_col=0))
A(callout("The audit log is append-only. Nothing — not even an operator — edits or deletes rows. "
          "Corrections are new compensating entries, exactly like case-field versioning.", kind="info"))

# ── 8. Integration ───────────────────────────────────────────────────────────
A(Paragraph("8 &nbsp;·&nbsp; Integration with the harness", sH1))
A(flow_row(["Case + complaint", "Harness selects formulation", "Fills + sends form", "Module fires + audits",
            "Harness assembles answer", "Resolution on case"]))
A(Spacer(1, 2 * mm))
A(Paragraph("Figure 3 — integration flow. The harness plans in formulations the way it already plans in "
            "tools; the worker, queue, approvals, and citations are v2.0 as built.", sCaption))
A(data_table(["Seam (v2.0, exists)", "What changes", "Size"], [
    ["Planner task flows", "Plan steps name formulations (CHECK.*, WRITE.*) per job family J1–J5", "Config + tests"],
    ["Policy gate", "Only two rules to enforce: checks pass freely; writes need approval + evidence + key",
     "Simpler than before"],
    ["Registry / runner", "Runner becomes a thin client of the module API (service token, envelope in/out)", "Small"],
    ["Approvals UI", "Approve/reject already exists; now explicitly releases a WRITE formulation", "None"],
    ["run_steps + citations", "Steps record formulation_id + evidence refs; check verdicts cited like chunks", "None"],
    ["Worker + queue", "Unchanged — leases, retries, resumes formulation calls like any step", "None"],
], widths=[40 * mm, 90 * mm, 40 * mm]))
A(Paragraph("What crosses the boundary, in either direction: filled forms and typed envelopes out; results "
            "and evidence refs back. What never crosses: credentials, connection strings, SQL, raw DB errors, "
            "full NINs.", sBody))

# ── 9. Mock + conformance ────────────────────────────────────────────────────
A(Paragraph("9 &nbsp;·&nbsp; Mock database + conformance suite", sH1))
A(Paragraph("The mock is a conformance stand-in, not a shortcut: deterministic seed data (profiles, "
            "vehicles, receipts, certificates, flags) behind a repository interface, with error injection "
            "(timeouts, 404s, downtime flags) so retry, fallback, and escalation paths are testable from day "
            "one.", sBody))
A(Paragraph("The conformance suite is the exam paper with an answer key that any backend — mock today, "
            "real CMR tomorrow — must pass identically before cutover:", sH2))
A(data_table(["#", "Exam question", "Must answer"], [
    ["1", "CHECK.receipt.lookup on known RRR", "status=paid + correct amount, date, account"],
    ["2", "CHECK.vehicle.lookup on unknown plate", "not-found envelope — never a crash, never invented data"],
    ["3", "WRITE.payment.link twice, same key", "One link; second call ignored with duplicate-key notice"],
    ["4", "WRITE without approval", "Refused with reason; zero DB effect, audit row still written"],
    ["5", "WRITE citing stale/missing evidence", "Refused; names the missing check verdict"],
    ["6", "Backend timeout on a CHECK", "Retryable error inside 5s; harness may retry"],
], widths=[10 * mm, 72 * mm, 88 * mm]))
A(callout("Cutover rule: the real CMR backend must score identically on the full suite before a single "
          "citizen case touches it. Write the suite now, while the mock is being built.", kind="info"))

# ── 10. Example + rails + build ──────────────────────────────────────────────
A(Paragraph("10 &nbsp;·&nbsp; Worked example: paid-but-unpaid (J4)", sH1))
A(data_table(["#", "Side", "Action", "Stored"], [
    ["1", "Harness", "Select CHECK.receipt.lookup, fill RRR", "Proposal + filled form"],
    ["2", "Module", "Fire check; verdict: paid, wrong account", "Audit row + evidence ref E-101"],
    ["3", "Harness", "Select WRITE.payment.link, fill RRR + account, cite E-101", "Approval requested"],
    ["4", "Operator", "Approve", "Approval ref A-77; task released"],
    ["5", "Module", "Fire write once (key K-55); re-check confirms link", "Audit rows; link_ref L-8812"],
    ["6", "Harness", "Assemble cited resolution", "Task completed on case"],
], widths=[10 * mm, 22 * mm, 62 * mm, 76 * mm]))
A(Paragraph("If the worker restarts after step 5, replay finds key K-55 completed and continues — the "
            "payment is never linked twice.", sBody))
A(Paragraph("Safety rails + build order", sH1))
for b in ["<b>Two verbs only.</b> Anything that is not a check or a write does not enter the catalog — "
          "OCR stays upstream, notifications downstream, doorway stays a doorway.",
          "<b>Writes never self-authorize, never blind-retry, never claim unverified success.</b>",
          "<b>Audit is append-only;</b> corrections are compensating entries.",
          "<b>Phase 2a:</b> module shell + mock + conformance suite + all 8 CHECKs → exit: complaints "
          "answered with live mock facts + citations; suite green.",
          "<b>Phase 2b:</b> first writes (WRITE.payment.link, WRITE.certificate.renew) → exit: one payment "
          "and one renewal fixed end to end, zero duplicates, approvals honored.",
          "<b>Phase 2c:</b> remaining writes + correction window ruling → exit: all five families pass safety "
          "tests; NPF confirms window rule and endpoint shapes for the real cutover."]:
    A(Paragraph(b, sBullet, bulletText="•"))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=20 * mm, bottomMargin=15 * mm,
                        title="CMR Specialist — Tool Module: Formulator & Firer (Phase 2 v3)",
                        author="CMR Specialist")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(f"Wrote {OUT}")
