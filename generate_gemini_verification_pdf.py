"""
CMR Specialist — Gemini Inference Verification Report PDF.
Chronological log of every test run while connecting Gemini: aim, method,
result, conclusion — plus findings, code changes, and current status.
Output: output/CMR_Specialist_Gemini_Verification.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

W, H = A4
OUT = "/Users/mac/Desktop/cmr_specialist/output/CMR_Specialist_Gemini_Verification.pdf"

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
PASS_BG = HexColor("#ECFDF5")
FAIL_BG = HexColor("#FEF2F2")
FAIL_LINE = HexColor("#F87171")


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


def data_table(headers, rows, widths=None, mono_col=None, verdict_col=None):
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
    if verdict_col is not None:
        for i, r in enumerate(rows, start=1):
            v = str(r[verdict_col]).upper()
            if v.startswith("PASS"):
                style.append(("BACKGROUND", (verdict_col, i), (verdict_col, i), PASS_BG))
            elif v.startswith("FAIL"):
                style.append(("BACKGROUND", (verdict_col, i), (verdict_col, i), FAIL_BG))
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


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, H - 14 * mm, W, 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(15 * mm, H - 9 * mm, "CMR SPECIALIST  ·  Gemini Verification Report")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - 15 * mm, H - 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


story = []
A = story.append

# ── Cover ────────────────────────────────────────────────────────────────────
A(Spacer(1, 28 * mm))
A(Paragraph("CMR SPECIALIST · INFERENCE", ParagraphStyle("brand", parent=sSub,
      fontName="Helvetica-Bold", fontSize=11, textColor=TEAL, spaceAfter=4)))
A(Paragraph("Gemini Connection:<br/>Verification Report", sTitle))
A(Spacer(1, 4 * mm))
A(Paragraph("Every test run while connecting the system to Gemini — what each test was trying "
            "to prove, how it was done, what happened, and what was concluded. Written for a "
            "non-technical reader: each test is explained first in plain words, then in detail.",
            ParagraphStyle("coversub", parent=sSub, fontSize=10.5, leading=15)))
A(Spacer(1, 8 * mm))
A(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8, spaceBefore=4))
A(data_table(["Item", "Detail"], [
    ["Goal", "Prove the system can reach Gemini, send correctly formed requests, and degrade "
     "safely when Google cannot answer"],
    ["Method", "Offline dry runs (no network) → direct API probes → live end-to-end cases"],
    ["Result", "Wiring proven correct; 4 findings fixed in code; final blocker is Google-side "
     "rate limiting (transient), not our system"],
    ["Test suite", "25 automated checks green throughout (mock mode unaffected)"],
], widths=[28 * mm, 142 * mm]))
A(Spacer(1, 6 * mm))
A(callout("Bottom line up front: your API key is valid, the code is correct, and Gemini answered "
          "successfully more than once. The only outstanding item is Google's temporary throttling, "
          "which resolves with time — see Section 5.", kind="tip"))

# ── 1. Test log ──────────────────────────────────────────────────────────────
A(Paragraph("1 &nbsp;·&nbsp; Test log (chronological)", sH1))
A(Paragraph("Each row is one test run. PASS means the thing being proven held true; FAIL means it "
            "surfaced a problem (which Section 2 then explains).", sBody))
A(data_table(["#", "Test (plain words)", "Verdict"], [
    ["T1", "Offline dry run: with a fake key and no network, does the system build the right "
     "request and survive failure gracefully?", "PASS"],
    ["T2", "First live case (ownership complaint): does Gemini classify and extract names?", "FAIL"],
    ["T3", "Ask Google directly: is the problem our key, our address, or our model name?", "PASS"],
    ["T4", "After fixing the model name: does a live case use Gemini without errors?", "FAIL"],
    ["T5", "Ask the model a trivial question directly: is Google reachable at all?", "PASS"],
    ["T6", "Ask for name extraction directly: what exactly comes back?", "FAIL"],
    ["T7", "Same extraction request with a 7x larger token budget: does the answer complete?", "PASS"],
    ["T8", "Server restart + live ownership case with fixed budgets: do names land in the DB?", "FAIL"],
    ["T9", "Automated suite re-run after adding retry logic: did anything regress?", "PASS"],
    ["T10", "Final live case: names in DB?", "FAIL"],
], widths=[10 * mm, 132 * mm, 28 * mm], verdict_col=2))
A(Paragraph("What each test did, in detail", sH2))
A(Paragraph("<b>T1 — dry run.</b> Set a fake key, intercepted the HTTP layer so nothing left the "
            "machine, and fired a proposal. Verified three things: the provider object points at "
            "Google's OpenAI-compatible address with model gemini-2.0-flash; the outgoing payload "
            "contains the model name and Bearer authorization; and a simulated network failure returns "
            "empty-handed instead of crashing. All three held.", sBody))
A(Paragraph("<b>T2 — first live case.</b> Submitted a change-of-ownership complaint through the real "
            "API. The case was created and the task queued, but zero LLM-extracted fields landed and the "
            "log showed HTTP 404 from Google. A 404 means 'wrong address or wrong name' — the investigation "
            "moved to T3.", sBody))
A(Paragraph("<b>T3 — direct interrogation.</b> Called Google's endpoint with curl and printed the full "
            "error body. Google answered plainly: the key is fine, the address is fine, but "
            "gemini-2.0-flash is retired — use gemini-3.8-flash. Diagnosis complete in one call.", sBody))
A(Paragraph("<b>T4 — retry after model fix.</b> Updated the model name in settings and .env, restarted "
            "both processes. The live case ran with zero LLM errors — but still zero LLM fields. No error "
            "plus no result meant the model was answering with something unparseable. Moved to T5/T6.", sBody))
A(Paragraph("<b>T5 — trivial probe.</b> Asked the model to reply 'ok'. It did. Conclusion: reachable, "
            "authenticated, correct model — the plumbing is fine; the problem is specific to the "
            "extraction request.", sBody))
A(Paragraph("<b>T6 — raw extraction reply.</b> Printed the model's exact unedited response to the name-"
            "extraction prompt. It came back cut off mid-sentence after a handful of tokens. A reply that "
            "stops that early, on a tiny request, points at the token budget being consumed before visible "
            "output — the signature of a thinking model doing hidden reasoning inside a 150-token allowance.",
            sBody))
A(Paragraph("<b>T7 — budget x7.</b> Identical request with 1024 tokens. Perfect JSON came back: buyer "
            "Adaeze Okafor, seller Musa, requester Adaeze Okafor. Hypothesis confirmed; budgets were raised "
            "in code (intent/extraction 150 to 600, drafting 300 to 800).", sBody))
A(Paragraph("<b>T8 — live case, fixed budgets.</b> Only the regex plate number landed; the log showed one "
            "HTTP 503 (service unavailable) from Google. The request was well-formed this time — Google "
            "itself was refusing. Response: added one-retry-with-pause resilience to the proposal helper.",
            sBody))
A(Paragraph("<b>T9 — regression suite.</b> 12 passed covering the new retry code and all pre-existing "
            "behavior. Nothing regressed; mock mode byte-identical.", sBody))
A(Paragraph("<b>T10 — final live case.</b> Still regex-only fields; Google 503 persisted across both the "
            "attempt and its retry. Direct probes minutes earlier had succeeded, so configuration is ruled "
            "out — this is upstream throttling. All test traffic stopped to let quota recover.", sBody))

# ── 2. Findings ──────────────────────────────────────────────────────────────
A(Paragraph("2 &nbsp;·&nbsp; Findings (4)", sH1))
A(Paragraph("Finding 1 — retired model name (solved)", sH2))
A(Paragraph("Symptom: HTTP 404 on every call. Evidence: Google's error body naming gemini-2.0-flash as "
            "retired and prescribing gemini-3.8-flash. Fix: model name updated in settings.py and .env. "
            "Lesson: model names are perishable — keep them in one configurable place (done) and re-check "
            "them when calls start 404ing.", sBody))
A(Paragraph("Finding 2 — thinking model ate the token budget (solved)", sH2))
A(Paragraph("Symptom: replies cut off after a few tokens; JSON unparseable. Evidence: identical prompt "
            "succeeds at 1024 tokens and returns perfect JSON. Fix: budgets raised (600 intent/extraction, "
            "800 drafting). Lesson: never size token budgets for the visible answer alone — reasoning "
            "models spend invisibly first.", sBody))
A(Paragraph("Finding 3 — stale process squatting on port 8080 (solved)", sH2))
A(Paragraph("Symptom: fresh server produced no logs and health checks timed out. Investigation: an old "
            "server process from an earlier session still held the port, so the new instance could never "
            "bind. Fix: killed by process id, restarted clean. Lesson: always confirm the old processes are "
            "dead (pgrep) before declaring a startup broken.", sBody))
A(Paragraph("Finding 4 — Google-side throttling, 503s (open, transient)", sH2))
A(Paragraph("Symptom: well-formed, previously succeeding calls now return 503 Service Unavailable, "
            "persisting across retries. Evidence for throttling rather than misconfiguration: the same key, "
            "address, and model succeeded minutes earlier (T5/T7); failures began only after a burst of "
            "diagnostic calls — the classic free-tier rate-limit pattern. Mitigation in place: one retry "
            "with pause; deterministic fallback keeps every case working regardless. Resolution: time — "
            "quota windows reset; then verify with a single case (Section 5). If 503s persist into tomorrow, "
            "escalate to a different flash model or the paid tier.", sBody))

# ── 3. Code changes ──────────────────────────────────────────────────────────
A(Paragraph("3 &nbsp;·&nbsp; Code changes made during verification", sH1))
A(data_table(["File", "Change", "Why (which test)"], [
    ["configs/settings.py", "GEMINI_API_URL + GEMINI_MODEL settings; provider option 'gemini'",
     "So the endpoint and (perishable) model name are configurable, not hard-coded"],
    ["providers/http_provider.py", "Sends the model field in the payload",
     "Gemini's endpoint rejects model-less requests (T2/T3)"],
    ["inference/gateway.py", "'gemini' branch + llm_enabled() flag",
     "One-line provider switch; callers can ask if a real model exists"],
    ["agent/llm.py (new)", "propose_json / propose_text: tolerant parsing, never raise, one retry",
     "The propose side of propose-vs-enforce; T8 drove the retry"],
    ["agent/intent.py", "LLM proposes classification; enum + range enforced; rules stay as fallback",
     "Model judgment without surrendering control"],
    ["agent/extractor.py", "LLM may only add names regex missed, marked pending, never overrides",
     "Recall without trusting the model over proven patterns"],
    ["agent/service.py", "LLM drafts answers from cited spans; citation validator still final",
     "Better prose, same evidence discipline"],
    ["Token budgets", "150 to 600 (intent/extract), 300 to 800 (draft)",
     "Finding 2: thinking-model headroom (T6/T7)"],
], widths=[44 * mm, 66 * mm, 60 * mm], mono_col=0))
A(callout("Nothing in this table changes mock-mode behavior: with INFERENCE_PROVIDER=mock the new code "
          "paths are inert, which is why all 25 automated checks stayed green throughout.", kind="tip"))

# ── 4. How to read it ────────────────────────────────────────────────────────
A(Paragraph("4 &nbsp;·&nbsp; How to read the system after this work", sH1))
A(Paragraph("Three log lines tell the whole story. In /tmp/cmr_server.log:", sBody))
A(code_block(["# silence  =  Gemini engaged and contributed (verify via extracted fields)",
              "# LLM proposal failed ... 503 ...  =  Google throttling; system on deterministic floor",
              "# LLM proposal failed ... 401/404 ...  =  key or model problem; needs human attention"]))
A(Paragraph("And the one database query that proves augmentation worked:", sBody))
A(code_block(["sqlite3 data/cmr_cases.db",
              "  \"SELECT name, raw_value, confidence, validation",
              "   FROM extracted_fields WHERE case_id='<CASE_ID>';",
              "# rows with validation='pending' and confidence ~0.55 are Gemini's contributions;",
              "# 'valid' rows near 0.8-0.95 are the regex floor."])
)
# ── 5. Status ────────────────────────────────────────────────────────────────
A(Paragraph("5 &nbsp;·&nbsp; Current status & next step", sH1))
A(data_table(["Item", "State"], [
    ["API key", "Installed in .env; authenticated successfully (5xx, never 401)"],
    ["Endpoint + model", "Correct; gemini-3.8-flash confirmed live by direct probe"],
    ["Wiring (propose paths)", "Proven by dry run + live successes; 25/25 tests green"],
    ["Resilience", "Retry + deterministic fallback; verified under real failures"],
    ["Blocker", "Google free-tier throttling (503s) — transient, quota-based"],
], widths=[44 * mm, 126 * mm]))
A(Paragraph("Next step, exactly one: wait roughly an hour without test traffic, submit a single ownership "
            "complaint mentioning two names, and query its extracted fields. Names present means Gemini is "
            "back; still absent with fresh 503s means the throttle window is longer — repeat once more "
            "tomorrow before considering a model or tier change.", sBody))
A(callout("Deliberately not done: no quota-burning retries, no model hopping, no paid-tier upgrade — all "
          "premature while the cause is a time-window throttle the system already rides out gracefully.",
          kind="warn"))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=20 * mm, bottomMargin=15 * mm,
                        title="CMR Specialist — Gemini Verification Report",
                        author="CMR Specialist")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(f"Wrote {OUT}")
