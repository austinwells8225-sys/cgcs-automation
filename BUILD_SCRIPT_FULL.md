# CGCS AI Intake — Build Script (Full)

## Project Name
CGCS Unified Agent (ai-intake)

## Overview
AI automation engine for the Center for Government & Civic Service at Austin Community College. Polls admin@cgcs-acc.org for Smartsheet event-space requests, classifies each as easy/mid/hard, creates a Google Calendar HOLD, appends a P.E.T. tracker row, and saves a Gmail draft reply (plus optional furniture/police drafts) for human approval.

## Tech Stack
- AI: Claude Sonnet 4 via LangChain Anthropic
- Agent: LangGraph 0.3 (StateGraph router pattern, 10 capability subgraphs)
- API: FastAPI 0.115
- DB: PostgreSQL 16 + asyncpg (12 tables under `cgcs` schema)
- Email/Calendar/Sheets: Google service account + domain-wide delegation
- Scheduler: APScheduler (single Uvicorn worker so jobs run once)
- Orchestration: N8N
- Deployment: Docker Compose on Coolify VPS
- Observability: LangSmith

## Structure
- `langgraph-agent/app/graph/` — router, nodes, edges, state
- `langgraph-agent/app/services/` — Gmail, Calendar, Sheets, classifier, processor, scheduler, inbox poller, agreement attacher
- `db/migrations/` — SQL migrations 001-011
- `cgcs-dashboard/` — Next.js 15 ops UI (Impact / Inbox / Alerts / Manual entry)
- `n8n/` — workflow JSON exports (legacy / fallback)
- `tests/` — pytest suite (604 tests)
- `credentials/` — Google service account JSON (gitignored)
- `docker-compose.yml` — 4 services (n8n, langgraph-agent, cgcs-dashboard, postgres)
- `PROJECT_STATE.md` — LLM-friendly snapshot of current state + roadmap

## Features
- Smartsheet intake pipeline: parse → classify → calendar HOLD → P.E.T. row → drafts
- Email triage with self-improving rejection patterns
- Email reply edit-loop with escalation detection
- Calendar availability check + holds
- P.E.T. tracker query/update with approval staging
- Event lead assignment + reminder scheduling (30d/14d/7d/48h)
- Daily digest (11 sections)
- Compliance checklist with deadlines
- Versioned line-item quotes
- Reports: revenue, conversion funnel, top orgs, compliance, process insights
- Dashboard alerts (AV/catering changes, dead-letter)
- Impact metrics: 4-tier rollup (Community / Monetization / ACC / CGCS) with YoY
- Manual off-site CGCS event entry endpoint
- Next.js operations dashboard (Impact homepage, Inbox, Manual entry, Alerts)
- Auto-attach correct CGCS user-agreement PDF (internal vs external) on first-reachout drafts
- Startup migration runner self-heals long-lived DBs

## Commands
- Start: `docker compose up -d`
- Tests: `PYTHONPATH=langgraph-agent python -m pytest tests/ -v`
- Health: `curl http://localhost:8000/api/v1/health`

## Prompts Up to date with Output

The CGCS AI intake system runs in human-in-the-loop draft-only mode (APScheduler polls admin@cgcs-acc.org every five minutes for `from:@app.smartsheet.com subject:"Notice of Event Space Request"`, runs each through the LangGraph smartsheet_intake subgraph which parses 40+ fields, classifies easy/mid/hard, creates a Google Calendar HOLD, appends a P.E.T. tracker row, and produces a Gmail draft reply plus optional furniture/police coordination drafts — the poller never sends, every reply waits in Drafts for Austin's approval); ACC's internal Smartsheet firewall now blocks delivery direct to admin@cgcs-acc.org so the inbound path is being rerouted via a new ACC Google Group `cgcs-group@austincc.edu` (Austin is a member with "Each email" subscription, and a Gmail filter on austin.wells@austincc.edu auto-forwards `from:(automation@app.smartsheet.com)` mail to admin@cgcs-acc.org while skipping his personal inbox — so Smartsheet → group → austin.wells → forward → admin → existing poller, zero code change required, waiting only on Michelle to update the Smartsheet form's destination address); the email-triage subgraph now also picks up first-reachout cold inquiries: the classifier returns an `is_initial_reachout` boolean alongside category/priority, the `draft_email_reply` node calls a new `agreement_attacher` service that picks the CGCS Internal vs External user-agreement PDF based on whether the sender's domain is in `{austincc.edu, cgcs-acc.org}` (default external for unknown domains — safer legal posture), loads the bundled PDF from `langgraph-agent/app/assets/agreements/`, and the Gmail draft is created with that attachment so reviewers approve a draft that's already legally complete; the system is paired with a Next.js operations dashboard scaffold at `cgcs-dashboard/` whose homepage is Bryan's four-tier impact rollup: Community (every event in the space — total events, total people, total hours, revenue), Monetization (events, people, hours, dollars), ACC (events, people, hours), and CGCS (events, people, total hours, training-hours-delivered, on-site vs off-site split, audience disaggregation by students/staff/community) with year-over-year deltas on every card; the dashboard also exposes an Inbox page that lists `/api/v1/email/pending` drafts with one-click approve/reject server actions, an Alerts page on `/api/v1/alerts/active`, and a manual-entry form for off-site CGCS events that posts to the new `/api/v1/events/manual` endpoint (off-site CGCS events live only in internal communications today, so the form is the only structured capture path); migration `011_impact_metrics.sql` adds `event_category`/`event_subtype`/`event_location` enums, `attendance_students`/`staff`/`community` columns, `training_hours_delivered`, a `canonical_events` + `canonical_event_aliases` table for the future de-dup pass Bryan flagged (River Hacks = Space Apps = NASA Space Apps), and a `cgcs.event_surveys` table for the planned 5-7 question post-event survey — existing reservation rows are best-effort retroactively classified by event-name and requester-email patterns, with everything unmatched defaulting to monetization so revenue still rolls up; the new Python module `app/db/impact_queries.py` runs the four tiers plus YoY in a single request, the impact endpoint mounts at `/api/v1/impact?period=year`, and `app/main.py` now imports `ImpactReportResponse`/`ManualEventRequest`/`ManualEventResponse` from `app/models.py`; docker-compose mounts migrations 005/007/008/009/010/011 into postgres init, exports GMAIL_DELEGATED_USER + SMARTSHEET_POLL_ENABLED + SMARTSHEET_POLL_MINUTES on the agent, and adds a `cgcs-dashboard` service (Coolify port 3000) wired with NextAuth Google OAuth restricted to @austincc.edu/@cgcs-acc.org via ALLOWED_EMAIL_DOMAINS; an LLM-friendly project snapshot lives at `PROJECT_STATE.md` in the repo root summarizing components, current state, and roadmap; remaining work to go live is (1) Michelle updates the Smartsheet form to send to cgcs-group@austincc.edu, (2) set real values in Coolify for ANTHROPIC_API_KEY/LANGGRAPH_API_KEY/WEBHOOK_SECRET/GOOGLE_CALENDAR_ID/PET_TRACKER_SPREADSHEET_ID/GMAIL_DELEGATED_USER plus NEXTAUTH_SECRET/GOOGLE_OAUTH_CLIENT_ID/GOOGLE_OAUTH_CLIENT_SECRET, (3) confirm Workspace DWD scopes for cgcs-acc.org (no austincc.edu DWD needed thanks to the forwarding-based path), (4) point CGCS-controlled DNS for api.cgcs-acc.org and ops.cgcs-acc.org at the Coolify VPS, (5) smoke-test one real Smartsheet email + one cold first-reachout email + render the Impact page, (6) build out the planned Reservations table (data ready, page is a stub), survey ingestion via a Google Form webhook into `cgcs.event_surveys`, and the canonical-event de-dup matcher when there's enough live data to validate it.

## Prompts RAW

1. hey where are we on the intake are we prepared for emails and we understand the process enough to draft replies?
2. claude
3. Hey can you explian where the ai intake is right now explian it to me like im 5
4. amazing whats the next steps to getting thsi live and going
5. right and we wanna get this on our own domain/ dashboard showing revenue tracking pending items and stuff like that
6. hey so where are we and what do we need to do to get this all going please and thank you
7. cgcs controls the cgcs-acc.org dashboard can be a group login once we get that going anyways continue to next steps
8. yeah lets do that also i want you to look at these notes from my boss from our meeting yesterday we want this dashboard live /Users/a2068129/Downloads/meeting_transcript.txt
9. Go with the existing reservation rows. I don't really know what that means, TVH. The off-site CGCS events live just like in our own internal communications. Yeah, yeah, I already have a server. Let's just keep going. Let's just build some stuff. We just need to get this done and it be able to do all the things here. We go. Let's go.
10. Hey I need you to tell me if there's a diff in the code that hasn't been pushed to main. Enumararte them and summarize it in one paragraph
11. ok so does the project has claude.md files or memory of what is the goal? y/n
12. ok. /analyze Do the most robust, detailed and LLM friendly markdown file that summarizes what the state of the project (where the project is right now) and where is it going.
