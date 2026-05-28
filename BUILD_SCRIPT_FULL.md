# CGCS AI Intake — Build Script (Full)

## Project Name
CGCS Unified Agent (ai-intake)

## Overview
AI automation engine for the Center for Government & Civic Service at Austin Community College. Ingests Smartsheet event-space requests via a manual paste-in `/intake` form on the dashboard (the prior admin@cgcs-acc.org Gmail poller is retired — ACC firewall blocks the mailbox and ACC Workspace blocks every Google API path the agent needed), classifies each as easy/mid/hard, creates a Google Calendar HOLD, writes a P.E.T. row to Postgres, and produces a reply draft (plus optional furniture/police coordination drafts) staged for human review.

## 2026-05-28 — admin@cgcs-acc.org cleanup + EMAIL_DRY_RUN kill switch

**Request:** Austin opened the architecture file at `~/Documents/Austin Vault/08_output/cgcs-ai-intake-architecture.md` and asked Claude to debug why the code repo cannot read his `austin.wells@austincc.edu` emails. Two-agent code+docs exploration surfaced the truth: the agent never tries to read his inbox — it impersonates `admin@cgcs-acc.org` via DWD and depends on a Gmail filter on Austin's ACC inbox forwarding Smartsheet notifications across. Austin then clarified that `admin@cgcs-acc.org` is fully dead (ACC firewall rejects delivery), Smartsheet notifications now hit his ACC inbox directly, and he wants the agent to read *his* inbox. Cross-referenced against the prior session's pivot notes (BUILD_SCRIPT.md), which already established that ACC Workspace blocks every Google API path the agent needs and the system was pivoted to a manual paste-in `/intake` form.

**Files changed:**

- **`langgraph-agent/app/cgcs_constants.py`** — `CGCS_SYSTEM_EMAIL` reassigned from `admin@cgcs-acc.org` to `austin.wells@austincc.edu` (with explanatory comment); `admin@cgcs-acc.org` removed from `ESCALATION_RECIPIENTS` list so escalations don't vanish into a black-hole mailbox.
- **`langgraph-agent/app/services/intake_classifier.py`** — signature lines at the end of the Easy reply (`:276`) and the Mid/Hard review reply (`:326`) swapped from `admin@cgcs-acc.org | www.cgcsacc.org` to `austin.wells@austincc.edu | www.cgcsacc.org`. These ship in real client emails.
- **`langgraph-agent/app/services/reply_processor.py`** — `EDIT_LOOP_LIMIT_MESSAGE` fallback contact text now points clients at `austin.wells@austincc.edu` instead of the dead admin address.
- **`langgraph-agent/app/models.py:614`** + **`langgraph-agent/app/main.py:1471`** + **`langgraph-agent/app/db/impact_queries.py:199`** — default `requester_email` for the manual-event endpoint and underlying query updated.
- **`langgraph-agent/app/config.py`** — added new `email_dry_run: bool = False` setting; changed default for `gmail_delegated_user` from `admin@cgcs-acc.org` to `austin.wells@austincc.edu` (env var still overrides; production `.env` is left untouched because the cutover requires ACC IT authorization first).
- **`langgraph-agent/app/services/gmail_service.py`** — added `EMAIL_DRY_RUN` guard to `send_email` (line ~190) and `reply_to_thread` (line ~290) — when true, both short-circuit with a `logger.warning` and return `{"message_id": "DRY_RUN", ...}` instead of calling the Gmail API. `create_draft_reply` is intentionally untouched (drafts never leave the Drafts folder, so they're always safe). Module docstring + `send_email`/`create_draft` docstrings updated to drop references to the dead admin mailbox.
- **`langgraph-agent/app/services/smartsheet_inbox_poller.py`** — module docstring updated to describe the configured `GMAIL_DELEGATED_USER` (not the hard-coded admin address).
- **`langgraph-agent/app/memories/rules.md`** — "All outbound emails from admin@cgcs-acc.org via Gmail API" updated to reflect the live address.
- **`.env.example`** — `GMAIL_DELEGATED_USER` flipped to `austin.wells@austincc.edu` with an explanatory block-comment about why; new `EMAIL_DRY_RUN=false` flag documented inline.
- **`scripts/test_gmail_read.py`** — new file. Read-only smoke test. Calls `gmail_service.read_inbox(query=SMARTSHEET_QUERY, max_results=5)` and prints sender/subject/date. Supports `--query` and `--max` flags. Designed to be the first thing run if/when ACC IT authorizes any Gmail auth path for the agent.
- **`tests/test_reply_processor.py`** — two assertions updated from `"admin@cgcs-acc.org"` to `"austin.wells@austincc.edu"` to match the new `EDIT_LOOP_LIMIT_MESSAGE` and the `process_email_reply` limit branch.
- **`tests/test_date_utils.py`** — `test_escalation_recipients` updated to assert length 2 and presence of Michelle + Austin (now that `admin@cgcs-acc.org` is removed).
- **`PROJECT_STATE.md`** — new section `0a. ARCHITECTURE PIVOT — 2026-05-28` inserted before the existing TL;DR. Records: the dead mailbox state, the in-prod `/intake` paste-in trigger, the cleanup landed this commit, and the three concrete asks any of which would unlock a return to email-reading (cross-org DWD on `austincc.edu`, OAuth refresh-token consent, or a service account inside an ACC-owned GCP project — all previously refused by ACC IT). Points at `~/.claude/plans/i-want-you-to-typed-rossum.md` for the full debugging trace.

**Not changed (intentional):**

- The local `.env` (gitignored) was NOT flipped. Production keeps `GMAIL_DELEGATED_USER=admin@cgcs-acc.org` until ACC IT authorizes a new path; flipping it now would just produce an `unauthorized_client` error from Google. The `config.py` *default* is updated so a fresh checkout or a missing env var fails loudly on the right identity.
- `SMARTSHEET_QUERY` in `smartsheet_inbox_poller.py` was NOT changed. The `is:unread` race (Austin marks notices read in Gmail before the poller picks them up) only matters once email-reading is actually live again. Flagged in `PROJECT_STATE.md` for the eventual cutover — recommended replacement is a Gmail-filter-applied label like `label:cgcs-intake-pending`.
- `cgcs-acc.org` was left in `cgcs-dashboard/.env:ALLOWED_EMAIL_DOMAINS`. Removing it would lock anyone with a legacy CGCS Google Workspace account out of the dashboard; keep it until the full decommission step in the plan.
- No OAuth refresh-token branch was added to `gmail_service._get_credentials`. The auth path remains DWD-only because (a) the prior session established ACC blocks OAuth too, and (b) the fallback only matters if Austin re-engages ACC IT and gets a different answer — premature to implement.

**Why:** `admin@cgcs-acc.org` was woven through outbound content as the "system email" — signatures, fallback contact text, CC field, manual-event defaults, escalation recipients. With the mailbox dead, every one of those locations was either misdirecting clients to a black hole or silently dropping data. The cleanup is correct regardless of which auth path eventually wins. The `EMAIL_DRY_RUN` kill switch is added now so the eventual cutover (whenever ACC IT unblocks something) can stage through shadow mode without a code change. The `PROJECT_STATE.md` banner is the most-read doc in the repo for cold-start LLMs — landing the current truth there means the next session doesn't repeat this same investigation.

**Verification once auth is unblocked:** `cd /Users/a2068129/Desktop/ai-intake && source langgraph-agent/.venv/bin/activate && python scripts/test_gmail_read.py` — should print 5 recent Smartsheet notifications from Austin's inbox. If it errors with `unauthorized_client`, the service account's OAuth client ID still isn't authorized for DWD on `austincc.edu`. If it errors with `invalid_grant`, the impersonated user doesn't exist in the target Workspace.

---

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

The CGCS AI intake system has pivoted away from an inbox-polling architecture because Austin Community College's Workspace admin blocks every Google API path the agent needed (no GCP project creation on austincc.edu, App Passwords disabled, third-party app access locked, Domain-Wide Delegation unavailable), so the inbound trigger is now a human-in-the-loop `/intake` page on the dashboard where Austin pastes the body of a Smartsheet "Notice of Event Space Request" email plus subject/sender, a Next.js server action POSTs it to the agent's existing `POST /webhook/smartsheet-new-entry` endpoint with the shared `WEBHOOK_SECRET`, and the LangGraph `smartsheet_intake` subgraph runs unchanged — parsing 40+ structured fields, classifying easy/mid/hard, attempting a Google Calendar HOLD (currently 403 until the service account is upgraded from "See all event details" to "Make changes to events" on the CGCS calendar), writing a P.E.T. row to Postgres via `create_minimal_reservation`, and producing a reply-to-requester acknowledgment plus optional furniture/police coordination drafts — the page then renders the parsed event as a key/value table alongside each drafted email with per-field copy buttons so Austin sends them from Gmail himself, with the new reservation auto-revalidating onto `/reservations`; that `/reservations` page IS the new P.E.T. (the Google Sheet was abandoned after the ACC shared-drive policy blocked sharing it with the service account) and renders 13 columns — Date, Event, Lead, Org, Tier (with the S/A/C single-letter badge where A=monetization/S=acc/C=cgcs and partner names like LangChain/ACM/Open Austin override to cgcs), Status, Revenue, Attendees, Ad Astra, Layout, Walkthrough, AV, Catering — every cell editable in place via the `InlineEditor` primitives (`InlineText`/`InlineNumber`/`InlineDate`/`InlineSelect`) that call a generic `updateFieldsAction` server action wrapping `PATCH /api/v1/reservations/{id}` whose `update_reservation_fields` query whitelists six categories of columns (TEXT, NUM, DATE, TIME, ENUM, META) and routes JSONB sub-keys into `source_metadata`; a `NewEventButton` modal lets any staff member add a row from scratch with only event_name + date + start/end required, posting through `POST /api/v1/reservations`; rows are sorted upcoming-first then most-recent-past, every row tinted by season (spring=green, summer=yellow, fall=amber) via a `seasonTint()` Tailwind helper, and an APScheduler job `auto_complete_past_events` runs hourly plus once at startup to flip any past `approved` row to `completed` so the table reflects calendar reality without admin action; a second job `calendar_sync` runs every 5 minutes pulling the CGCS Google Calendar (calendar id `c_afaea34169f9e252afd545081e551f140dcefa691c2a8fcd8c6f9cec1c0c4f9d@group.calendar.google.com`) into reservations with the same S/A/C classifier (`SMARTSHEET_POLL_ENABLED=false`, `CALENDAR_SYNC_ENABLED=true`); migrations 012 (`cgcs_lead` text + `source_metadata` JSONB) and 013 (`fiscal_years` + `ledger_transactions` for the budget page) are mounted into postgres init and also COPY'd into the agent image so prod bootstrap doesn't depend on bind mounts; the dashboard Dockerfile pins `ENV HOSTNAME=0.0.0.0` for Next.js standalone, `lib/api.ts` wraps every agent fetch in a 5-second AbortController so `next build` can't hang on "Collecting page data", and the dashboard service in compose now also exports `WEBHOOK_SECRET` so the `/intake` server action can authenticate; n8n still runs in compose as a future-proofing artifact but is unused — when n8n self-hosted asked for a Client ID/Secret to set up Gmail OAuth, that path was abandoned in favor of the manual `/intake` form because ACC blocks creating the necessary GCP OAuth client; the end-to-end test using the real "Texas Housers 2026 Houser Awards" Smartsheet email succeeded — agent parsed 40+ fields, classified as "hard" (weekend event needing police), drafted 3 emails, failed only at calendar HOLD and Sheet writes (both permission issues being tracked separately); remaining work is (1) Austin upgrades the service account from "See all event details" to "Make changes to events" on the CGCS calendar so HOLDs write, (2) Coolify production deploy revived (parked — schema bootstrap diagnostic in #49), (3) refresh P.E.T. from latest spreadsheet exports (#58), (4) build the impact rollup homepage cards against the real reservation data, and (5) if ACC ever opens third-party app access, swap the `/intake` page for an automated Gmail trigger in n8n hitting the same webhook with zero agent changes.

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
13. yes build /intake
