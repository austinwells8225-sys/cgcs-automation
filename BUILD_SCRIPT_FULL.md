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
- `langgraph-agent/app/services/` — Gmail, Calendar, Sheets, classifier, processor, scheduler, inbox poller
- `db/migrations/` — SQL migrations 001-010
- `n8n/` — workflow JSON exports
- `tests/` — pytest suite
- `credentials/` — Google service account JSON (gitignored)
- `docker-compose.yml` — 3 services (n8n, langgraph-agent, postgres)

## Features
- Smartsheet intake pipeline: parse → classify → calendar HOLD → P.E.T. row → drafts
- Email triage with self-improving rejection patterns
- Email reply edit-loop with escalation detection
- Calendar availability check + holds
- P.E.T. tracker query/update with approval staging
- Event lead assignment + reminder scheduling
- Daily digest (11 sections)
- Compliance checklist with deadlines
- Versioned line-item quotes
- Reports: revenue, conversion funnel, top orgs, compliance, process insights
- Dashboard alerts
- Impact metrics: 4-tier rollup (Community / Monetization / ACC / CGCS) with YoY
- Manual off-site CGCS event entry endpoint
- Next.js operations dashboard (Impact homepage, Inbox, Manual entry, Alerts)

## Commands
- Start: `docker compose up -d`
- Tests: `PYTHONPATH=langgraph-agent python -m pytest tests/ -v`
- Health: `curl http://localhost:8000/api/v1/health`

## Prompts Up to date with Output

The CGCS AI intake system runs in human-in-the-loop draft-only mode (APScheduler polls admin@cgcs-acc.org every five minutes for `from:@app.smartsheet.com subject:"Notice of Event Space Request"`, runs each through the LangGraph smartsheet_intake subgraph which parses 40+ fields, classifies easy/mid/hard, creates a Google Calendar HOLD, appends a P.E.T. tracker row, and produces a Gmail draft reply plus optional furniture/police coordination drafts — the poller never sends, every reply waits in Drafts for Austin's approval) and is now paired with a Next.js operations dashboard scaffold at `cgcs-dashboard/` whose homepage is Bryan's four-tier impact rollup: Community (every event in the space — total events, total people, total hours, revenue), Monetization (events, people, hours, dollars), ACC (events, people, hours), and CGCS (events, people, total hours, training-hours-delivered, on-site vs off-site split, audience disaggregation by students/staff/community) with year-over-year deltas on every card; the dashboard also exposes an Inbox page that lists `/api/v1/email/pending` drafts with one-click approve/reject server actions, an Alerts page on `/api/v1/alerts/active`, and a manual-entry form for off-site CGCS events that posts to the new `/api/v1/events/manual` endpoint (off-site CGCS events live only in internal communications today, so the form is the only structured capture path); migration `011_impact_metrics.sql` adds `event_category`/`event_subtype`/`event_location` enums, `attendance_students`/`staff`/`community` columns, `training_hours_delivered`, a `canonical_events` + `canonical_event_aliases` table for the future de-dup pass Bryan flagged (River Hacks = Space Apps = NASA Space Apps), and a `cgcs.event_surveys` table for the planned 5-7 question post-event survey — existing reservation rows are best-effort retroactively classified by event-name and requester-email patterns, with everything unmatched defaulting to monetization so revenue still rolls up; the new Python module `app/db/impact_queries.py` runs the four tiers plus YoY in a single request, the impact endpoint mounts at `/api/v1/impact?period=year`, and `app/main.py` now imports `ImpactReportResponse`/`ManualEventRequest`/`ManualEventResponse` from `app/models.py`; docker-compose mounts migrations 005/007/008/009/010/011 into postgres init, exports GMAIL_DELEGATED_USER + SMARTSHEET_POLL_ENABLED + SMARTSHEET_POLL_MINUTES on the agent, and adds a `cgcs-dashboard` service (Coolify port 3000) wired with NextAuth Google OAuth restricted to @austincc.edu/@cgcs-acc.org via ALLOWED_EMAIL_DOMAINS; remaining work to go live is (1) set real values in Coolify for ANTHROPIC_API_KEY/LANGGRAPH_API_KEY/WEBHOOK_SECRET/GOOGLE_CALENDAR_ID/PET_TRACKER_SPREADSHEET_ID/GMAIL_DELEGATED_USER plus NEXTAUTH_SECRET/GOOGLE_OAUTH_CLIENT_ID/GOOGLE_OAUTH_CLIENT_SECRET, (2) confirm Workspace DWD scopes, (3) point CGCS-controlled DNS for api.cgcs-acc.org and ops.cgcs-acc.org at the Coolify VPS, (4) smoke-test one real Smartsheet email + render the Impact page, (5) build out the planned Reservations table (data ready, page is a stub), survey ingestion via a Google Form webhook into `cgcs.event_surveys`, and the canonical-event de-dup matcher when there's enough live data to validate it.

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
