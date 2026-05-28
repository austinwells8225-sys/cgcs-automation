# CGCS AI Intake — Build Script

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

A standalone Obsidian-flavored mermaid architecture diagram of the entire CGCS AI intake repo (high-level system topology, the LangGraph router fanning out to 10 capability subgraphs, the Smartsheet intake sequence, Docker Compose service layout, and an ER diagram of the 12 Postgres tables) was generated and saved to `~/Documents/Austin Vault/08_output/cgcs-ai-intake-architecture.md` as a self-contained reference note with frontmatter tags `[diagram, architecture, cgcs, ai-intake]`. The CGCS AI intake system has pivoted away from an inbox-polling architecture because Austin Community College's Workspace admin blocks every Google API path the agent needed (no GCP project creation on austincc.edu, App Passwords disabled, third-party app access locked, Domain-Wide Delegation unavailable), so the inbound trigger is now a human-in-the-loop `/intake` page on the dashboard where Austin pastes the body of a Smartsheet "Notice of Event Space Request" email plus subject/sender, a Next.js server action POSTs it to the agent's existing `POST /webhook/smartsheet-new-entry` endpoint with the shared `WEBHOOK_SECRET`, and the LangGraph `smartsheet_intake` subgraph runs unchanged — parsing 40+ structured fields, classifying easy/mid/hard, attempting a Google Calendar HOLD (currently 403 until the service account is upgraded from "See all event details" to "Make changes to events" on the CGCS calendar), writing a P.E.T. row to Postgres via `create_minimal_reservation`, and producing a reply-to-requester acknowledgment plus optional furniture/police coordination drafts — the page then renders the parsed event as a key/value table alongside each drafted email with per-field copy buttons so Austin sends them from Gmail himself, with the new reservation auto-revalidating onto `/reservations`; that `/reservations` page IS the new P.E.T. (the Google Sheet was abandoned after the ACC shared-drive policy blocked sharing it with the service account) and renders 13 columns — Date, Event, Lead, Org, Tier (with the S/A/C single-letter badge where A=monetization/S=acc/C=cgcs and partner names like LangChain/ACM/Open Austin override to cgcs), Status, Revenue, Attendees, Ad Astra, Layout, Walkthrough, AV, Catering — every cell editable in place via the `InlineEditor` primitives (`InlineText`/`InlineNumber`/`InlineDate`/`InlineSelect`) that call a generic `updateFieldsAction` server action wrapping `PATCH /api/v1/reservations/{id}` whose `update_reservation_fields` query whitelists six categories of columns (TEXT, NUM, DATE, TIME, ENUM, META) and routes JSONB sub-keys into `source_metadata`; a `NewEventButton` modal lets any staff member add a row from scratch with only event_name + date + start/end required, posting through `POST /api/v1/reservations`; rows are sorted upcoming-first then most-recent-past, every row tinted by season (spring=green, summer=yellow, fall=amber) via a `seasonTint()` Tailwind helper, and an APScheduler job `auto_complete_past_events` runs hourly plus once at startup to flip any past `approved` row to `completed` so the table reflects calendar reality without admin action; a second job `calendar_sync` runs every 5 minutes pulling the CGCS Google Calendar (calendar id `c_afaea34169f9e252afd545081e551f140dcefa691c2a8fcd8c6f9cec1c0c4f9d@group.calendar.google.com`) into reservations with the same S/A/C classifier (`SMARTSHEET_POLL_ENABLED=false`, `CALENDAR_SYNC_ENABLED=true`); migrations 012 (`cgcs_lead` text + `source_metadata` JSONB) and 013 (`fiscal_years` + `ledger_transactions` for the budget page) are mounted into postgres init and also COPY'd into the agent image so prod bootstrap doesn't depend on bind mounts; the dashboard Dockerfile pins `ENV HOSTNAME=0.0.0.0` for Next.js standalone, `lib/api.ts` wraps every agent fetch in a 5-second AbortController so `next build` can't hang on "Collecting page data", and the dashboard service in compose now also exports `WEBHOOK_SECRET` so the `/intake` server action can authenticate; n8n still runs in compose as a future-proofing artifact but is unused — when n8n self-hosted asked for a Client ID/Secret to set up Gmail OAuth, that path was abandoned in favor of the manual `/intake` form because ACC blocks creating the necessary GCP OAuth client; the end-to-end test using the real "Texas Housers 2026 Houser Awards" Smartsheet email succeeded — agent parsed 40+ fields, classified as "hard" (weekend event needing police), drafted 3 emails, failed only at calendar HOLD and Sheet writes (both permission issues being tracked separately); remaining work is (1) Austin upgrades the service account from "See all event details" to "Make changes to events" on the CGCS calendar so HOLDs write, (2) Coolify production deploy revived (parked — schema bootstrap diagnostic in #49), (3) refresh P.E.T. from latest spreadsheet exports (#58), (4) build the impact rollup homepage cards against the real reservation data, and (5) if ACC ever opens third-party app access, swap the `/intake` page for an automated Gmail trigger in n8n hitting the same webhook with zero agent changes.
