#!/usr/bin/env python3
"""
Backfill completed events from Austin's pasted spreadsheet dump into
cgcs.reservations. Source = 'manual_backfill' so they're distinguishable
from Smartsheet-ingested rows.

Mapping rules (confirmed with Austin):
  Internal-S/A   -> event_category = 'acc'
  Internal-C     -> event_category = 'cgcs'
  External-S/A   -> event_category = 'monetization'
  External-C     -> event_category = 'cgcs'

Skipped rows are listed at the end of the run.
"""
from __future__ import annotations
import subprocess, sys, re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Row:
    name: str
    classification: str          # e.g. "Internal-S", "External-A"
    date: str                    # ISO YYYY-MM-DD
    start: str                   # HH:MM:SS
    end: str                     # HH:MM:SS
    room: str                    # event_hall | classroom | small_conference
    revenue: float = 0.0
    email: str = "unknown@unknown.com"
    name_poc: str = "Unknown"
    org: Optional[str] = None
    smartsheet_id: Optional[str] = None
    attendees: Optional[int] = None
    notes: Optional[str] = None
    skip_reason: Optional[str] = None


# Helper: map S/A/C + Internal/External to event_category
def category_for(classification: str) -> str:
    c = classification.lower().replace(" ", "")
    if "internal" in c:
        return "cgcs" if c.endswith("c") else "acc"
    # external
    return "cgcs" if c.endswith("c") else "monetization"


# Helper: subtype heuristic
def subtype_for(name: str, category: str) -> str:
    n = name.lower()
    if any(k in n for k in ("training", "orientation", "cohort", "fellows", "workshop")):
        return "training"
    if any(k in n for k in ("convening", "summit", "conference", "retreat", "meetup")):
        return "convening"
    if category == "cgcs":
        return "co_branded"
    return "other"


# All rows. Manually parsed from Austin's dump. Year inferred from order:
# July-Dec rows = 2025; Jan-May rows = 2026.
ROWS: list[Row] = [
    Row("Opportunity Austin Economic Development Council Meeting", "External-S",
        "2025-07-10", "11:00:00", "13:00:00", "event_hall", 0,
        "egori@opportunityaustin.com", "Elizabeth Gori", "Opportunity Austin"),
    Row("Army Future Commands", "External-S",
        "2025-07-15", "07:00:00", "19:00:00", "event_hall", 0,
        "david.vargas1@army.mil", "David Vargas", "U.S. Army",
        smartsheet_id="20250618-00044"),
    Row("Federal Highway Association's Autonomous Vehicle Meeting", "External-A",
        "2025-07-22", "08:00:00", "17:00:00", "event_hall", 1060,
        "krisatrevino@gmail.com", "Kris A Trevino", "City of Austin",
        smartsheet_id="20250611-00039"),
    Row("Women In Cyber Security (Jul 23)", "External-S",
        "2025-07-23", "18:00:00", "21:00:00", "classroom", 0,
        "macysgirl1@gmail.com", "Silvia Patricia González-Villaseñor", "WiCyS",
        smartsheet_id="20250714-00051"),
    Row("Army Software Factory Cohort", "Internal-S",
        "2025-07-24", "12:00:00", "16:00:00", "event_hall", 0,
        "jennifer.houlihan@austincc.edu", "Jennifer Houlihan", "ACC / ASWF",
        smartsheet_id="20250716-00075"),
    Row("CGCS Environmental Summit", "Internal-C",
        "2025-07-25", "10:00:00", "17:00:00", "event_hall", 0,
        "austin.wells@austincc.edu", "Austin Wells", "CGCS",
        smartsheet_id="20250703-00044"),
    Row("Skull Games Task Force Weekend (day 1)", "External-S",
        "2025-08-02", "09:00:00", "17:00:00", "event_hall", 0,
        "liz@skullgames.io", "Liz Bradt", "Skull Games",
        smartsheet_id="20250703-00004",
        notes="Multi-day 8/2-8/3. Time approximate (not provided)."),
    Row("Army Software Factory - Promotion Reception", "External-S",
        "2025-08-08", "12:30:00", "14:30:00", "event_hall", 500,
        "samantha.farone.civ@swf.army.mil", "Samantha Farone", "U.S. Army SWF",
        smartsheet_id="20250710-00043"),
    Row("MCSWF Meet", "Internal-S",
        "2025-08-12", "12:00:00", "14:00:00", "small_conference", 0,
        "jeffery.l.averette.mil@swf.army.mil", "Jeffery Averette", "MCSWF",
        smartsheet_id="20250714-00103"),
    Row("Bats to Cats Faculty Orientation", "Internal-S",
        "2025-08-19", "10:00:00", "15:00:00", "event_hall", 0,
        "gpotts@austincc.edu", "Grant Potts", "ACC Faculty",
        smartsheet_id="20250721-00030"),
    Row("ACC AEG Department Meeting", "Internal-S",
        "2025-08-20", "10:30:00", "14:30:00", "event_hall", 0,
        "rdayton@austincc.edu", "Rachel Dayton", "ACC AEG Department",
        smartsheet_id="20250707-00081"),
    Row("Faculty Senate Retreat", "Internal-A",
        "2025-08-22", "11:00:00", "14:00:00", "event_hall", 0,
        "arojo@austincc.edu", "Alona Rojo", "ACC Faculty Senate",
        smartsheet_id="20250715-00049"),
    Row("Women In Cyber Security (Sep 4)", "External-S",
        "2025-09-04", "18:00:00", "21:00:00", "classroom", 0,
        "macysgirl1@gmail.com", "Silvia Patricia González-Villaseñor", "WiCyS",
        smartsheet_id="20250811-00035"),
    Row("TPW Leadership Summit", "External-A",
        "2025-09-10", "08:00:00", "16:00:00", "event_hall", 1060,
        "natalie.rodriguez@austintexas.gov", "Natalie Rodriguez", "TPW / City of Austin",
        smartsheet_id="20250812-00049"),
    Row("LangChain AI Meetup", "External-S",
        "2025-09-10", "17:00:00", "21:30:00", "event_hall", 0,
        "colin@2cups.com", "Colin McNamara", "LangChain Austin",
        smartsheet_id="20250811-00041"),
    Row("Women In Cyber Security (Sep 11)", "External-S",
        "2025-09-11", "18:00:00", "21:00:00", "classroom", 0,
        "macysgirl1@gmail.com", "Silvia Patricia González-Villaseñor", "WiCyS",
        smartsheet_id="20250811-00036"),
    Row("Dream Come True Foundation", "External-A",
        "2025-09-17", "17:00:00", "22:00:00", "event_hall", 0,
        "yvette@everyonesdreamcometrue.org", "Yvette", "Dream Come True Foundation",
        smartsheet_id="20250813-00129"),
    Row("International Day of Peace Event", "Internal-S",
        "2025-09-19", "16:00:00", "20:00:00", "event_hall", 0,
        "matthew.mandell@austincc.edu", "Matthew Mandell",
        "ACC Center for Peace & Conflict Studies",
        smartsheet_id="20250812-00035"),
    Row("ACM Austin Meetup (Sep 23)", "External-S",
        "2025-09-23", "18:00:00", "20:30:00", "event_hall", 0,
        "akshaycanodia@gmail.com", "Akshay Mittal", "ACM Austin",
        smartsheet_id="20250915-00037"),
    Row("OSI Team Meeting", "Internal-S",
        "2025-09-22", "14:00:00", "16:00:00", "classroom", 0,
        "cjones12@austincc.edu", "Cyndie Jones", "ACC OSI",
        smartsheet_id="20250819-00006"),
    Row("Riverhacks", "Internal-C",
        "2025-10-04", "09:00:00", "17:00:00", "small_conference", 0,
        "marisela.perezmaita@austincc.edu", "Marisela Perez", "CGCS",
        notes="Multi-day Oct 4-5."),
    Row("Tri-Department Meeting and Luncheon", "Internal-S",
        "2025-10-10", "10:00:00", "15:00:00", "event_hall", 0,
        "lucinda.smither@austincc.edu", "Lucy Smither", "ACC",
        smartsheet_id="20250922-00047"),
    Row("CGCS Journalism Summit", "Internal-C",
        "2025-10-11", "10:00:00", "17:00:00", "event_hall", 0,
        "marisela.perezmaita@austincc.edu", "Marisela Perez", "CGCS",
        smartsheet_id="20250820-00065"),
    Row("Educate Texas", "External-A",
        "2025-10-14", "09:00:00", "16:00:00", "event_hall", 2850,
        "lhendricks@cftexas.org", "Lauren Hendricks", "Communities Foundation of Texas",
        smartsheet_id="20250507-00032",
        notes="Multi-day Oct 14-17."),
    Row("Catch The Next Fall Seminar", "Internal-S",
        "2025-10-23", "07:30:00", "17:30:00", "event_hall", 0,
        "susan.wynne@austincc.edu", "Susan Wynne", "ACC Student Affairs",
        smartsheet_id="20250529-00037",
        notes="Multi-day Oct 23-24."),
    Row("United Way Event (Oct 27)", "External-A",
        "2025-10-27", "13:00:00", "16:30:00", "event_hall", 0,
        "matt.thompson@uwatx.org", "Matt Thompson", "United Way Austin",
        smartsheet_id="20251013-00020"),
    Row("Red Bench Event", "Internal-S",
        "2025-10-28", "18:00:00", "21:00:00", "event_hall", 0,
        "rschneid@austincc.edu", "Regina Schneider",
        "ACC Office of Experiential Learning",
        smartsheet_id="20250529-00018"),

    # ---- November rows (column order shifted in source dump) ----
    Row("E3 Alliance Cradle to Career Cohort Collaboration Convening", "Internal-S",
        "2025-11-06", "06:30:00", "12:00:00", "event_hall", 0,
        "camelia.trahan@austincc.edu", "Camelia Trahan", "E3 Alliance / ACC",
        smartsheet_id="20250707-00110", attendees=86),
    Row("Great Questions Foundation Faculty Fellows Convening", "Internal-S",
        "2025-11-07", "08:00:00", "17:00:00", "event_hall", 0,
        "gpotts@austincc.edu", "Grant Potts", "Great Questions Foundation",
        smartsheet_id="20250717-00042", attendees=30,
        notes="Used multiple rooms: 3340, 3328, 3344, 3345, 3346, 3347, 3348."),
    Row("Civic Engagement Simulation U.T. Austin", "Internal-C",
        "2025-11-08", "13:00:00", "17:00:00", "event_hall", 0,
        "marisela.perezmaita@austincc.edu", "Marisela Perez", "CGCS / UT Austin",
        smartsheet_id="20250820-00073", attendees=25),
    Row("Texas Housers - Houser Awards", "External-A",
        "2025-11-12", "12:00:00", "14:30:00", "event_hall", 1160,
        "isla@texashousing.org", "Isla Ruiz", "Texas Housers",
        smartsheet_id="20250819-00044", attendees=70),
    Row("United Way / Success By Six - Fall Wellness Event", "External-A",
        "2025-11-14", "09:00:00", "13:00:00", "event_hall", 250,
        "kara.hedlund@uwatx.org", "Kara Hedlund", "United Way Austin",
        smartsheet_id="20250812-00050", attendees=60),
    Row("Civic Leadership Simulation", "Internal-C",
        "2025-11-18", "15:00:00", "16:30:00", "event_hall", 0,
        "marisela.perezmaita@austincc.edu", "Marisela Perez", "CGCS",
        smartsheet_id="20251001-00131", attendees=25,
        notes="Multi-day Nov 18 & 20."),
    Row("JEM Employee Mixers / ACC-AAWCC Gratitude Mixer", "Internal-S",
        "2025-11-19", "10:00:00", "14:00:00", "event_hall", 0,
        "michelle.raymond@austincc.edu", "Michelle Raymond", "ACC AAWCC"),
    Row("Community Non-Profit Gathering (Correctional Education Dept)", "Internal-S",
        "2025-11-20", "11:00:00", "15:00:00", "event_hall", 0,
        "misty.campbell@austincc.edu", "Misty Campbell",
        "ACC Correctional Education", smartsheet_id="20251027-00060", attendees=35),
    Row("ACM Monthly Meetups (Nov)", "External-S",
        "2025-11-25", "17:00:00", "21:00:00", "event_hall", 0,
        "akshaycanodia@gmail.com", "Akshay Mittal", "ACM Austin",
        smartsheet_id="20251106-00039", attendees=45),
    Row("CGCS Holiday Party", "Internal-C",
        "2025-12-01", "17:00:00", "20:00:00", "event_hall", 0,
        "bryan.port@austincc.edu", "Bryan Port", "CGCS",
        smartsheet_id="20251027-00053", attendees=30),
    Row("Texas Sunshines Banquet (Lauren Braxton via Tagvenue)", "External-A",
        "2025-12-04", "18:00:00", "20:00:00", "event_hall", 200,
        "lauren.braxton@icloud.com", "Lauren Braxton", "Texas Sunshines", attendees=85),
    Row("ACC Police Department Awards Ceremony", "Internal-S",
        "2025-12-06", "17:00:00", "21:00:00", "event_hall", 0,
        "aryel.bazan@austincc.edu", "Sgt. Aryel Bazan", "ACC Police",
        smartsheet_id="20251111-00001", attendees=120),
    Row("ECHO Capacity Building Cohort", "External-A",
        "2025-12-09", "17:00:00", "20:00:00", "event_hall", 700,
        "marissa.vogel@austintexas.gov", "Marissa Vogel", "ECHO / City of Austin",
        smartsheet_id="20251120-00037", attendees=100),
    Row("Greater Austin YMCA: All Staff Meeting", "External-A",
        "2025-12-11", "12:00:00", "15:00:00", "event_hall", 2000,
        "kelli.keetell@greaterymca.org", "Kelli Keetell", "Greater Austin YMCA",
        smartsheet_id="20251120-00036", attendees=120),
    Row("ASWF Holiday Party", "Internal-A",
        "2025-12-13", "12:00:00", "16:00:00", "event_hall", 500,
        "michael.e.kirl.mil@swf.army.mil", "Michael Kirl", "ASWF", attendees=75),
    Row("ASWF Training", "Internal-S",
        "2025-12-18", "08:00:00", "16:00:00", "event_hall", 0,
        "michael.e.kirl.mil@swf.army.mil", "ASWF Lead", "ASWF",
        smartsheet_id="20251118-00087", attendees=74,
        notes="Setup Dec 18, day-of Dec 19. POC email not in dump; reused ASWF contact."),

    # ---- 2026 rows ----
    Row("Library Services All Circulation Meeting", "Internal-S",
        "2026-01-07", "07:00:00", "13:00:00", "event_hall", 0,
        "annelise.bretch@austincc.edu", "Annelise Bretch", "ACC Library Services",
        smartsheet_id="2025-06582", attendees=45),
    Row("BiggerPockets Workshop", "External-A",
        "2026-01-15", "12:00:00", "17:00:00", "event_hall", 760,
        "alexandra@biggerpockets.com", "Alexandra Pailet", "BiggerPockets",
        smartsheet_id="20251218-00022", attendees=70),
    Row("Texas Lyceum Orientation", "External-A",
        "2026-01-16", "07:00:00", "15:00:00", "event_hall", 1000,
        "info@texaslyceum.org", "Marine Bibes", "Texas Lyceum",
        smartsheet_id="20251218-00024", attendees=40),
    Row("United Way - UWATX Board Retreat", "External-A",
        "2026-01-23", "08:00:00", "17:00:00", "event_hall", 250,
        "julia.campbell@uwatx.org", "Julia Campbell", "United Way Austin",
        smartsheet_id="20251218-00028", attendees=50),
    Row("ACM Austin Monthly Meetups (Jan)", "External-C",
        "2026-01-27", "17:00:00", "20:00:00", "event_hall", 0,
        "akshaycanodia@gmail.com", "Akshay Mittal", "ACM Austin",
        smartsheet_id="20251218-00032", attendees=50),
    Row("IE Report (Chancellor's Office)", "Internal-C",
        "2026-01-28", "07:00:00", "17:00:00", "event_hall", 0,
        "elopez1@austincc.edu", "Eric Lopez", "ACC Chancellor's Office",
        smartsheet_id="20251105-00007", attendees=80),
    Row("Facilitation Lab Summit 2026", "External-A",
        "2026-02-16", "07:00:00", "18:00:00", "event_hall", 3000,
        "jamie@voltagecontrol.com", "Jamie LaFrenier", "Voltage Control",
        smartsheet_id="20260114-00053", attendees=140,
        notes="Multi-day Feb 16-18."),
    Row("ACC State of the College", "Internal-S",
        "2026-02-19", "08:00:00", "21:00:00", "event_hall", 0,
        "michelle.raymond@austincc.edu", "Michelle Raymond", "ACC",
        smartsheet_id="20251123-00002", attendees=150),
    Row("ADHD + Sensory Workshop", "External-A",
        "2026-02-20", "12:00:00", "16:00:00", "event_hall", 400,
        "cdejongh@hightophealth.com", "Carolina de Jongh", "High Top Health",
        smartsheet_id="20260210-00061", attendees=70),
    Row("Central Regional Partners / Attivo Partners", "External-A",
        "2026-02-24", "09:00:00", "17:00:00", "event_hall", 2500,
        "khebert@attivopartners.com", "Kylee Hebert", "Attivo Partners",
        smartsheet_id="20260114-00058", attendees=35,
        notes="Multi-day Feb 24-26."),
    Row("Celebration of Life for Mike Rieman", "External-A",
        "2026-02-27", "12:00:00", "17:00:00", "event_hall", 500,
        "patterson@pattersonbarrett.com", "Patterson Barrett",
        "Friends of Mike Rieman", smartsheet_id="20260123-00020", attendees=80),
    Row("Community Conversation on Educating Character", "Internal-S",
        "2026-03-10", "18:00:00", "20:00:00", "event_hall", 500,
        "ajohn@austincc.edu", "Arun John", "ACC LEAD", attendees=100),
    Row("Sobremesa", "Internal-S",
        "2026-03-26", "17:00:00", "21:00:00", "event_hall", 0,
        "samuel.carrillo@austincc.edu", "Samuel Carrillo", "ACC",
        smartsheet_id="20260220-00068", attendees=100,
        notes="POC email not in dump; assumed @austincc.edu."),
    Row("SD14 Convention", "External-A",
        "2026-03-28", "08:00:00", "16:00:00", "event_hall", 1500,
        "gamurphy7@yahoo.com", "Greg Murphy", "SD14",
        smartsheet_id="20260210-00088", attendees=200),
    Row("City of Austin - T.C. Broadnax Community Conversations", "External-A",
        "2026-03-30", "16:00:00", "20:00:00", "event_hall", 0,
        "unknown@cityofaustin.org", "Unknown POC", "City of Austin",
        smartsheet_id="20260324-00068", attendees=125,
        notes="POC email not in dump."),
    Row("Red Bench: Conversations that Matter", "Internal-S",
        "2026-03-31", "14:00:00", "21:00:00", "event_hall", 0,
        "rschneid@austincc.edu", "Regina Schneider", "ACC",
        smartsheet_id="20251118-00074", attendees=140),
    Row("ACC Awards Dinner", "Internal-S",
        "2026-04-09", "17:00:00", "21:00:00", "event_hall", 0,
        "aimee.finney@austincc.edu", "Aimee Finney", "ACC",
        smartsheet_id="20250929-00023"),
    Row("Daughters of the American Revolution - Opening Reception", "External-C",
        "2026-04-14", "11:00:00", "20:00:00", "event_hall", 0,
        "katy@calvertlindsay.com", "Katy Lindsay", "DAR", attendees=150),
    Row("Open Austin", "External-C",
        "2026-04-21", "17:00:00", "21:00:00", "event_hall", 0,
        "liani@open-austin.org", "Liani Lye", "Open Austin"),
    Row("ACM Monthly Meetup (Apr)", "External-S",
        "2026-04-22", "17:00:00", "21:00:00", "event_hall", 0,
        "akshaycanodia@gmail.com", "Akshay Mittal", "ACM Austin",
        smartsheet_id="20260407-00041"),
    Row("GAVA Funder Convening", "Internal-S",
        "2026-04-24", "09:00:00", "15:00:00", "event_hall", 700,
        "cassie@goaustinvamosaustin.org", "Cassie Sodergren", "GAVA",
        smartsheet_id="20260210-00055"),
    Row("Daughters of the American Revolution - Community Day", "External-C",
        "2026-04-25", "08:00:00", "17:00:00", "event_hall", 0,
        "katy@calvertlindsay.com", "Katy Lindsay", "DAR"),
    Row("NSIC | Association of the U.S. Army Monthly Breakfast", "External-A",
        "2026-05-19", "08:00:00", "12:00:00", "event_hall", 0,
        "dscheberle@nsictexas.org", "Drew Scheberle", "NSIC", attendees=100,
        notes="Revenue TBD at time of dump."),
    Row("ACC Viscom Grad Showcase", "Internal-S",
        "2026-05-13", "09:00:00", "22:00:00", "event_hall", 0,
        "viscom@austincc.edu", "ACC Viscom", "ACC Viscom",
        smartsheet_id="20260224-00096", attendees=175,
        notes="POC email not in dump; placeholder used."),

    # ---- Skipped (left here so the report shows them) ----
    Row("2026 Longhorn Lavender Graduation", "External-A",
        "2026-05-07", "14:00:00", "20:00:00", "event_hall", 1000,
        "unknown@unknown.com", "Vanessa", "Longhorn Lavender Grad",
        smartsheet_id="20260210-00115",
        skip_reason="Column order corrupted in dump: $200 / $1,000 mixed into wrong fields. Verify in source."),
    Row("Legacy of Leaders ACC Student Life", "Internal-S",
        "2026-04-15", "00:00:00", "00:00:00", "event_hall", 0,
        "drme.martinez@austincc.edu", "Dr. Mona-Elo Martinez", "ACC Student Life",
        skip_reason="Time listed as TBD."),
]


def sql_escape(s: Optional[str]) -> str:
    if s is None:
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def build_sql() -> tuple[str, list[Row], list[Row]]:
    inserted: list[Row] = []
    skipped: list[Row] = []
    sql_parts = [
        "-- Backfill of completed events. Generated by seed_completed_events.py.",
        "BEGIN;",
    ]
    for i, r in enumerate(ROWS, start=1):
        if r.skip_reason:
            skipped.append(r)
            continue
        category = category_for(r.classification)
        subtype = subtype_for(r.name, category)
        request_id = r.smartsheet_id or f"backfill-{i:03d}"
        completed_at = f"{r.date} {r.end}+00"
        sql_parts.append(f"""
INSERT INTO cgcs.reservations (
    request_id, requester_name, requester_email, requester_organization,
    event_name, requested_date, requested_start_time, requested_end_time,
    room_requested, actual_revenue, actual_attendance,
    event_category, event_subtype, event_location,
    status, source, completed_at, admin_notes
) VALUES (
    {sql_escape(request_id)},
    {sql_escape(r.name_poc)},
    {sql_escape(r.email)},
    {sql_escape(r.org)},
    {sql_escape(r.name)},
    {sql_escape(r.date)},
    {sql_escape(r.start)},
    {sql_escape(r.end)},
    {sql_escape(r.room)}::room_type,
    {r.revenue},
    {'NULL' if r.attendees is None else r.attendees},
    {sql_escape(category)}::cgcs.event_category,
    {sql_escape(subtype)}::cgcs.event_subtype,
    'on_site'::cgcs.event_location,
    'completed'::reservation_status,
    'manual_backfill',
    {sql_escape(completed_at)}::timestamptz,
    {sql_escape(r.notes)}
)
ON CONFLICT DO NOTHING;""")
        inserted.append(r)
    sql_parts.append("COMMIT;")
    return "\n".join(sql_parts), inserted, skipped


def main(argv: list[str]) -> int:
    sql, inserted, skipped = build_sql()
    if "--dry-run" in argv or "--show-sql" in argv:
        print(sql)
        return 0

    print(f"Inserting {len(inserted)} rows; skipping {len(skipped)}.\n")
    # Pipe SQL to psql inside the postgres container.
    result = subprocess.run(
        ["docker", "exec", "-i", "ai-intake-postgres-1",
         "psql", "-U", "cgcs_admin", "-d", "cgcs_events", "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True, capture_output=True,
    )
    if result.returncode != 0:
        print("psql failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return 1
    print(result.stdout)

    if skipped:
        print("\nSkipped rows (need manual cleanup in source):")
        for r in skipped:
            print(f"  - {r.name} ({r.date}): {r.skip_reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
