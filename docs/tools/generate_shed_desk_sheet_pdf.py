"""
Shed desk sheet + data rules, one printable PDF (2 pages).
Output: output/CMR_Specialist_Shed_Desk_Sheet.pdf (system python3).
"""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, PageBreak)

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = str(ROOT / "docs" / "output" / "CMR_Specialist_Shed_Desk_Sheet.pdf")
TEAL = HexColor("#0F766E")
INK = HexColor("#1E293B")
MUTED = HexColor("#64748B")
LINE = HexColor("#CBD5E1")
BLUE_BG = HexColor("#EFF6FF")

S_TITLE = ParagraphStyle("t", fontSize=26, leading=30, textColor=TEAL, alignment=TA_CENTER)
S_SUB = ParagraphStyle("s", fontSize=11, leading=14, textColor=MUTED, alignment=TA_CENTER)
S_H = ParagraphStyle("h", fontSize=14, leading=17, textColor=TEAL, spaceBefore=10, spaceAfter=4)
S_B = ParagraphStyle("b", fontSize=11, leading=15, textColor=INK, spaceAfter=4)
S_BUL = ParagraphStyle("bul", parent=S_B, leftIndent=12, bulletIndent=4, spaceAfter=3)
S_CELL = ParagraphStyle("cell", parent=S_B, fontSize=10, leading=13)
S_SIG = ParagraphStyle("sig", fontSize=10, leading=14, textColor=MUTED)

story = []
A = story.append


def bullets(items):
    for b in items:
        A(Paragraph(b, S_BUL, bulletText="\u2022"))


def tbl(headers, rows, widths):
    data = [[Paragraph(f"<b>{h}</b>", S_CELL) for h in headers]]
    for r in rows:
        data.append([Paragraph(c, S_CELL) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE_BG),
                           ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    A(t)


# PAGE 1 — desk sheet
A(Spacer(1, 10 * mm))
A(Paragraph("CMR Specialist - Desk Sheet", S_TITLE))
A(Paragraph("Pin this by the console. One page. Everything else is in the manual.", S_SUB))
A(HRFlowable(width="100%", thickness=1, color=LINE))
A(Paragraph("Start your day", S_H))
bullets(["Open the console in your browser (address from your supervisor).",
         "Sign in with YOUR username and password. Never share logins."])
A(Paragraph("The three statuses", S_H))
tbl(["You see", "It means", "You do"],
    [["waiting_for_input", "The system needs a missing fact", "Read the prompt, supply the answer as a follow-up (Card 2)"],
     ["waiting_approval", "A sensitive step needs a human", "Check the evidence, Approve or Reject with a reason"],
     ["plan: template (fallback)", "The AI was quiet; safe defaults ran", "Double-check the result before acting on it"]],
    [52 * mm, 58 * mm, 60 * mm])
A(Paragraph("Golden rules", S_H))
bullets(["Payments first (read-only, safest). Ownership transfers second. Anything awaiting approval waits - do not work around it.",
         "Knowledge answers without cited sources are the system saying 'I don't know' - treat them that way.",
         "Stuck? Call: ____________________ (write the support number here)."])

A(PageBreak())

# PAGE 2 — data rules
A(Spacer(1, 10 * mm))
A(Paragraph("CMR Specialist - Data Rules (Pilot)", S_TITLE))
A(Paragraph("Read, sign, return to your supervisor. One page.", S_SUB))
A(HRFlowable(width="100%", thickness=1, color=LINE))
A(Paragraph("What the system stores", S_H))
bullets(["Case texts you type; names, plate numbers, NINs, phone numbers, emails, and Remita receipt numbers contained in them.",
         "Your username on every case, approval, and upload you make.",
         "Published procedure documents uploaded to the knowledge base."])
A(Paragraph("Who may see it", S_H))
bullets(["Pilot team members only, signed in with their own logins.",
         "Nothing leaves the office system without written supervisor approval."])
A(Paragraph("How long it lives", S_H))
bullets(["Cases and their data are automatically deleted 90 days after creation.",
         "Knowledge documents live until unpublished by a supervisor.",
         "Audit rows keep no case link after purge (what happened is kept; whose data it was is not)."])
A(Paragraph("Your duties", S_H))
bullets(["Use your own login. Log out at end of day on shared machines.",
         "Report suspected misuse or data exposure immediately.",
         "Do not paste data about non-consenting third parties beyond the case at hand."])
A(Spacer(1, 12 * mm))
A(Paragraph("Name: ______________________________ &nbsp;&nbsp; Signature: ______________________________ &nbsp;&nbsp; Date: __________", S_SIG))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                        topMargin=14 * mm, bottomMargin=14 * mm, title="Shed Desk Sheet + Data Rules")
doc.build(story)
print("wrote", OUT)
