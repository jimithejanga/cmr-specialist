"""
VM/Internet pilot deployment architecture PDF for a first-time operator.
Output: docs/output/CMR_Specialist_Pilot_Deployment.pdf (system python3).
"""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = str(ROOT / "docs" / "output" / "CMR_Specialist_Pilot_Deployment.pdf")

TEAL = HexColor("#0F766E")
INK = HexColor("#1E293B")
MUTED = HexColor("#64748B")
LINE = HexColor("#CBD5E1")
CODE_BG = HexColor("#0F172A")
BLUE_BG = HexColor("#EFF6FF")
GREEN_BG = HexColor("#ECFDF5")
AMBER_BG = HexColor("#FFFBEB")

S_TITLE = ParagraphStyle("t", fontSize=24, leading=28, textColor=TEAL, alignment=TA_CENTER)
S_SUB = ParagraphStyle("s", fontSize=10, leading=14, textColor=MUTED, alignment=TA_CENTER)
S_H1 = ParagraphStyle("h1", fontSize=15, leading=18, textColor=TEAL, spaceBefore=14, spaceAfter=5)
S_H2 = ParagraphStyle("h2", fontSize=11.5, leading=15, textColor=INK, spaceBefore=9, spaceAfter=3)
S_B = ParagraphStyle("b", fontSize=9.4, leading=13.6, textColor=INK, spaceAfter=3)
S_BUL = ParagraphStyle("bul", parent=S_B, leftIndent=12, bulletIndent=4, spaceAfter=2)
S_NUM = ParagraphStyle("num", parent=S_BUL)
S_CODE = ParagraphStyle("c", fontSize=7.8, leading=10.4, textColor=white)
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


def tbl(headers, rows, widths=None):
    widths = widths or [42 * mm, 64 * mm, 64 * mm]
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


def steps(items):
    for i, b in enumerate(items, 1):
        A(Paragraph(b, S_NUM, bulletText=f"{i}."))


def h1(t):
    A(Paragraph(t, S_H1))
    A(HRFlowable(width="100%", thickness=0.7, color=LINE))


def h2(t):
    A(Paragraph(t, S_H2))


def p(t):
    A(Paragraph(t, S_B))


A(Spacer(1, 18 * mm))
A(Paragraph("Pilot Deployment Architecture", S_TITLE))
A(Paragraph("Hosting the CMR Specialist in the office or on the internet (VM) -<br/>a complete, beginner-friendly guide: what to get, how to set it up,<br/>how to run it daily, and how to fix it", S_SUB))
A(Spacer(1, 6 * mm))
p("You do not need to be a server expert. This guide assumes you can rent a virtual machine (a computer that lives on the internet instead of your desk), copy files to it, and run commands by pasting them. Every step tells you what you are doing and why. By the end, the system runs day and night without your laptop, staff use it from their browsers, data is backed up, and you know exactly what healthy looks like.")

h1("1. The Big Picture (What You Are Building)")
p("Today the system runs on a laptop: it sleeps when the lid closes and dies with the disk. The pilot moves it onto one always-on virtual machine (VM) - a rented computer in a data center, or a small server in the office. Five programs run on it:")
tbl(["Program", "Job", "Who can reach it"],
    [["Caddy (front door)", "Encrypts traffic (HTTPS), forwards browsers to the app", "Everyone (the only public face)"],
     ["Web (the app)", "Console, admin site, API", "Only Caddy (hidden inside)"],
     ["Worker (the engine)", "Runs queued tasks in the background", "Nobody directly - it reads the database"],
     ["Postgres (the safe)", "Stores everything durably", "Only web + worker"],
     ["Backup (the photocopier)", "Copies the database nightly, prunes old copies", "Writes to its own disk + offsite"]],
    [38 * mm, 66 * mm, 66 * mm])
p("Think of it as an office: Caddy is the receptionist at the single entrance, web serves the counter, worker toils in the back room, Postgres is the safe, backup photocopies the ledger every night. Staff never walk past reception.")

h1("2. What You Need Before You Start")
h2("2.1 The virtual machine")
bullets([
    "<b>Size:</b> 2 virtual CPUs, 4-8 GB memory, 40 GB disk. This system idles near zero; the headroom is for the database and uploaded PDFs. Anything sold as a 'small' server qualifies.",
    "<b>System:</b> Ubuntu 22.04 LTS (long-term support - boring and stable, which is what you want).",
    "<b>Where:</b> any provider (AWS, Azure, DigitalOcean, Hetzner, or a local host) - or a mini-PC/old desktop in the office running Ubuntu. The architecture is identical; only the address changes.",
    "<b>Cost:</b> a small VM rents for roughly $6-12/month; office hardware is free if spare. AI usage stays at cents per day.",
])
h2("2.2 A name (for internet hosting)")
p("If staff reach it over the internet, you want <i>cmr.youroffice.com</i> instead of bare numbers. Buy or use an existing domain, then create one DNS 'A record' pointing that name at the VM's public IP. This takes 10 minutes at any registrar and up to an hour to spread worldwide. Pure office-LAN pilots can skip this and use the private IP (e.g. 192.168.1.50) - but then there is no encrypted certificate from the internet, so prefer a real name even internally if you can.")
h2("2.3 Secrets you must prepare (never in git)")
bullets([
    "Your OpenRouter API key (the INFERENCE_API_KEY you already have).",
    "A long random database password (generate: <i>openssl rand -hex 24</i>).",
    "A first admin username + strong password (you will create it on first boot).",
    "Keep these in a password manager, and later in the VM's .env file only.",
])

h1("3. Setting Up the VM (Step by Step)")
steps([
    "<b>Log in.</b> <i>ssh user@YOUR-VM-IP</i>. You are now typing on the rented computer. Everything below happens there.",
    "<b>Install the two tools.</b> Docker (runs the five programs as sealed boxes) and Git (fetches the code). Ubuntu commands: <i>sudo apt update &amp;&amp; sudo apt install -y docker.io docker-compose-plugin git</i>, then log out and back in so Docker permissions apply.",
    "<b>Fetch the deployable line.</b> <i>git clone https://github.com/jimithejanga/cmr-specialist.git &amp;&amp; cd cmr-specialist &amp;&amp; git checkout next/stage2</i>. Note: the VM runs the <i>next/stage2</i> line, never main - main stays the untouched proven engine.",
    "<b>Write the secrets file.</b> Copy <i>.env.example</i> to <i>.env</i> and fill the real values: database password, inference key, domain name. Set permissions: <i>chmod 600 .env</i> (only you can read it).",
    "<b>Open the firewall.</b> Allow ports 80 and 443 (web) and 22 (your SSH only): <i>sudo ufw allow 80,443/tcp &amp;&amp; sudo ufw allow from YOUR-OFFICE-IP to any port 22 &amp;&amp; sudo ufw enable</i>. Everything else stays closed - the database port is never exposed.",
    "<b>Start everything.</b> <i>docker compose -f docker/docker-compose.yml up -d --build</i>. Five containers rise: db, web, worker, backup, caddy. Check: <i>docker compose ps</i> (all 'running') and <i>curl -s http://localhost:8080/health</i> (status ok).",
    "<b>Create the first admin safely.</b> Over your SSH connection (encrypted tunnel, never the open web), create the first user - it auto-becomes admin - then sign in at <i>https://YOUR-DOMAIN/admin</i> and confirm the ADMIN badge. Create each staff member's login while signed in as admin.",
    "<b>Prove the backup.</b> Run the backup once by hand, list the backup volume (one fresh timestamped file), then practice a restore on a scratch copy. A backup you have never restored is a rumor, not a backup.",
])
p("Total: an afternoon the first time, under an hour once practiced.")

h1("4. How the Pieces Fit (Architecture Detail)")
h2("4.1 Traffic path")
code(["staff browser --HTTPS(443)--> Caddy --HTTP--> web:8080 --SQL--> Postgres",
      "worker --SQL--> Postgres        backup --SQL--> Postgres (dump only)",
      "NOBODY --> Postgres directly (no published port except inside compose)"])
p("Caddy gets its certificate automatically (Let's Encrypt) the first time your domain points at it - no manual certificate work. HTTP on port 80 exists only to redirect to HTTPS.")
h2("4.2 Where state lives")
tbl(["State", "Lives in", "Survives restart?", "Backed up?"],
    [["Cases, users, tasks, audit", "Postgres volume pg_data", "yes", "yes (nightly dump)"],
     ["Nightly dumps (14 days)", "Volume pg_backups + offsite copy", "yes", "that IS the backup"],
     ["Uploaded knowledge PDFs", "harness_data volume", "yes", "include in offsite copy"],
     ["Admin test inserts (overlay)", "var-equivalent volume", "yes", "no (test data, reseedable)"],
     ["Secrets (.env)", "VM file, root-only", "yes", "NO - kept in password manager"]],
    [48 * mm, 52 * mm, 36 * mm, 34 * mm])
h2("4.3 Releases and rollback (no-merge rule)")
p("The VM runs <i>next/stage2</i> image tags (vm-shed-1, vm-shed-2...). A deploy is: pull, rebuild, restart - two commands, under two minutes of downtime (or zero with a second web replica). A rollback is: restart the previous tag - one command. Fixes from the proven <i>main</i> line arrive only by deliberate cherry-pick, never by merge, so the office never inherits an accidental change. Each deploy is recorded (tag + date + what changed) in a one-line release log.")

h1("5. Daily Operations (The Routine)")
h2("5.1 Morning (30 seconds, anyone)")
bullets([
    "Open the admin Worker page: heartbeat fresh, queue near zero, no (fallback) badge clusters.",
    "If the queue age climbs: the worker is down - restart that one container, watch it drain.",
])
h2("5.2 Staff routine")
bullets([
    "Sign in with personal logins; never share. Log out on shared machines.",
    "Payments first (read-only, safest), ownership second; WRITE-gated work only after the approval habit exists.",
    "Fallback badge means 'the AI was quiet' - double-check that result before acting.",
])
h2("5.3 Weekly (admin, 10 minutes)")
bullets([
    "Confirm a fresh backup file exists AND the offsite copy timestamp is current.",
    "Glance at disk use (uploads accumulate) and the approval log for anomalies.",
    "Rotate nothing unless someone left - then disable their account immediately.",
])

h1("6. When Things Break (Troubleshooting for Beginners)")
tbl(["Symptom", "Likely cause", "Fix"],
    [["Site won't load", "VM off / Caddy down / DNS wrong", "Provider console: VM running? Then: compose ps; dig YOUR-DOMAIN (IP match?)"],
     ["Login fails for everyone", "DB container down", "compose ps; restart db, then web+worker (order matters)"],
     ["Tasks stuck queued", "Worker down", "Admin Worker page heartbeat stale - restart worker container only"],
     ["Certificate warning", "Brand-new domain / DNS just changed", "Wait up to an hour; Caddy retries automatically"],
     ["Disk full", "Uploads or old backups", "Prune backups past 14 days; move old knowledge PDFs to archive"],
     ["Forgot admin password", "Human memory", "SSH in, use the password-reset procedure (documented in runbook); never email passwords"]],
    [38 * mm, 52 * mm, 80 * mm])
p("Golden rule: containers are disposable, volumes are precious. Never delete a volume to 'fix' something - restart the container instead. Data loss comes from volume commands, never from restarts.")

h1("7. Costs, Limits, and What Comes Next")
tbl(["Item", "Pilot scale", "Notes"],
    [["VM + domain", "~$6-12/month + ~$10/year", "office hardware: free"],
     ["AI inference", "cents/day", "flash-class model, paced + cached"],
     ["Staff time", "30-sec mornings + 10-min weeklies", "plus two shadow weeks at launch"],
     ["Capacity", "5-20 staff, hundreds of cases/day", "single web + single worker; second web replica is the first scale step"]],
    [40 * mm, 60 * mm, 70 * mm])
p("What this pilot deliberately excludes: citizen portal, supervisor dashboards, live-update plumbing, second API version, microservices. After a month of real use, staff requests - not guesses - decide what gets built next, on the <i>next/stage2</i> line, behind a new image tag.")

A(Spacer(1, 6 * mm))
A(Paragraph("Generated 2026-09-27 - CMR Specialist pilot deployment guide. Companion: docs/output/CMR_Specialist_Agent_Manual.pdf - Generator: docs/tools/generate_pilot_deployment_pdf.py", S_CAP))

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                        topMargin=14 * mm, bottomMargin=14 * mm,
                        title="CMR Specialist - Pilot Deployment Architecture")
doc.build(story)
print("wrote", OUT)
