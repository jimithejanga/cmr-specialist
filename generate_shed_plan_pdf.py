"""
Shed Pilot Plan PDF: deployment, locks, git workflow, noted future UIs.
Output: output/CMR_Specialist_Shed_Plan.pdf (system python3).
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

OUT = "/Users/mac/Desktop/cmr_specialist/output/CMR_Specialist_Shed_Plan.pdf"

TEAL = HexColor("#0F766E")
INK = HexColor("#1E293B")
MUTED = HexColor("#64748B")
LINE = HexColor("#CBD5E1")
CODE_BG = HexColor("#0F172A")
BLUE_BG = HexColor("#EFF6FF")
white = HexColor("#FFFFFF")

S_TITLE = ParagraphStyle("t", fontSize=24, leading=28, textColor=TEAL, alignment=TA_CENTER)
S_SUB = ParagraphStyle("s", fontSize=10, leading=14, textColor=MUTED, alignment=TA_CENTER)
S_H1 = ParagraphStyle("h1", fontSize=15, leading=18, textColor=TEAL, spaceBefore=14, spaceAfter=5)
S_H2 = ParagraphStyle("h2", fontSize=11.5, leading=15, textColor=INK, spaceBefore=9, spaceAfter=3)
S_B = ParagraphStyle("b", fontSize=9.4, leading=13.4, textColor=INK, spaceAfter=3)
S_BUL = ParagraphStyle("bul", parent=S_B, leftIndent=12, bulletIndent=4, spaceAfter=2)
S_CODE = ParagraphStyle("c", fontSize=8, leading=10.5, textColor=white)
S_CAP = ParagraphStyle("cap", fontSize=8, leading=10, textColor=MUTED, alignment=TA_CENTER)
S_CELL = ParagraphStyle("cell", parent=S_B, fontSize=8.4, leading=11)

story = []
A = story.append


def code(lines):
    rows = [[Paragraph(f"<font face='Courier'>{l}</font>", S_CODE)] for l in lines]
    t = Table(rows, colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                           ("ROUNDEDCORNERS", [3, 3, 3, 3]),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    A(t)
    A(Spacer(1, 2 * mm))


def tbl(headers, rows, widths):
    data = [[Paragraph(f"<b>{h}</b>", S_CELL) for h in headers]]
    for r in rows:
        data.append([Paragraph(c, S_CELL) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE_BG),
                           ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    A(t)
    A(Spacer(1, 2 * mm))


def bullets(items):
    for b in items:
        A(Paragraph(b, S_BUL, bulletText="\u2022"))


def h1(t):
    A(Paragraph(t, S_H1))
    A(HRFlowable(width="100%", thickness=0.7, color=LINE))


def h2(t):
    A(Paragraph(t, S_H2))


def p(t):
    A(Paragraph(t, S_B))


A(Spacer(1, 20 * mm))
A(Paragraph("The Shed", S_TITLE))
A(Paragraph("Pilot deployment plan for the CMR Specialist (v2.0 - office use)", S_SUB))
A(Spacer(1, 6 * mm))
p("Take the proven system exactly as it is - no new features - and give it a safe, locked, backed-up home where office colleagues can use it daily. Same console, same workflows. Just no longer on a laptop.")
p("Analogy: a good generator sits in your bedroom on your power, with one shared key to the front door. The shed moves it outside into a locked shed with its own keys, nightly photocopies of the papers, and instructions pinned on the door.")

h1("1. The five pieces")
h2("Piece 1 - A home: one always-on machine")
p("A spare office PC, mini-PC, or small rented server (2 CPUs / 4 GB RAM is plenty). It runs the same two programs (web + worker) and starts them automatically on boot. From that day, nobody depends on any individual's laptop.")
h2("Piece 2 - The locks: a login system")
p("Every staff member gets a username and password and signs in through the console. Three ideas inside:")
bullets([
    "<b>Identity</b> - 'who are you?' Every case, approval, and upload carries a real name. Anonymous approvals are theater; named approvals are accountability.",
    "<b>Session</b> - 'the hand stamp.' One login gives the browser a temporary token; no password-typing per click. It expires (e.g. end of day) so forgotten browsers stop being trusted.",
    "<b>Revocation</b> - 'changing the lock.' Disable the account when someone leaves; their access dies instantly. No shared secret to rotate, no memo to the whole office.",
])
p("Locks are not encryption (HTTPS, also included via a free Caddy front door) and not yet permissions - every logged-in staff member can do everything. Roles come later.")
h2("Piece 3 - A safe: Postgres plus nightly backup")
p("Flip one setting (DATABASE_URL) from the current SQLite file to Postgres - the compose file already exists in the repo. One scheduled nightly job copies the database to a second location: worst case after a failure is losing a day, never everything. A 90-day auto-purge rides on the same mechanism so old personal data deletes itself.")
h2("Piece 4 - The rules: one page on data")
p("Written, not coded: what the system stores (names, plates, NINs, receipts), who may see it (pilot team only), how long it lives (90 days), who approves exceptions. Staff acknowledge it. Cheapest piece, biggest legal protection.")
h2("Piece 5 - The desk sheet: one page for staff")
p("How to open the console. Three statuses in plain words: <i>needs your input</i> (answer the prompt), <i>needs approval</i> (a human must confirm), <i>fallback badge</i> (the AI was quiet - check the result twice). One phone number for problems.")

h1("2. A day in the shed")
bullets([
    "Morning: everything is already running. Staff open a browser tab and work cases.",
    "Payment reconciliation first (read-only, safest), ownership transfers second. Nothing WRITE-gated until the approval habit exists.",
    "The screen reports its own problems (badges, prompts, queue states); nobody reads logs.",
    "Night: the backup runs alone. Nobody maintains anything.",
])
p("Cost and time: software effectively free (compose file, Caddy, Postgres all in-repo or free). About a day of setup plus half a day of staff walkthrough. Daily AI cost: cents.")

h1("3. Git workflow (standing rule)")
p("All shed work is built on <b>branches</b>, never by rebuilding. <i>main</i> always boots; each job gets a branch (shed/login-system, shed/postgres-backup, ...), merges after tests pass, then the branch is deleted. When the shed is done and running, <i>main</i> is tagged as the new version. Commits stay small and readable; .env is never committed.")
code(["git checkout -b shed/login-system   # workspace per job",
      "# ... work, commit small, push, open PR against main ...",
      "# tests green -> merge -> delete branch",
      "git tag v2.1-shed   # version = milestone, when the shed ships"])

h1("4. Noted future UI work (not in the shed)")
tbl(["UI", "Purpose", "Guardrail"],
    [["MockDB viewer/editor", "Browse + insert test data (RRRs, plates, NINs) without SQL", "TEST-labeled, synthetic rows only; never wired to a real registry"],
     ["Harness DB viewer", "Read-only trace of cases, fields, tasks, steps, audits", "Read-only: all state changes stay in the API"],
     ["Worker monitor", "Liveness, leased task, queue depth, recent outcomes", "Read-only; no log files needed"],
     ["Bulk knowledge upload", "Many PDFs/docs at once, live counter (uploaded vs published)", "Upload stages; publishing still required per version"]],
    [42 * mm, 66 * mm, 62 * mm])
p("Build order when the time comes: mockDB editor first (unblocks test setup), harness viewer second, worker monitor third, bulk upload alongside knowledge work.")

h1("5. What stays out - and why")
p("No citizen portal, supervisor dashboard, live-update plumbing, or second API version. Each is a guess about what staff will need. The shed converts guesses into requests: after a month of real use, the team will say exactly which piece of the target architecture to build first - and they will be right, because they will be speaking from the work.")

A(Spacer(1, 6 * mm))
A(Paragraph("Generated 2026-09-26 - CMR Specialist v2.0 shed plan. Status: described, not yet built.", S_CAP))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                        topMargin=14 * mm, bottomMargin=14 * mm, title="The Shed - Pilot Plan")
doc.build(story)
print("wrote", OUT)
