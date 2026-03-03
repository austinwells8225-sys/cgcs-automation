# CGCS Unified Agent

AI-powered automation engine for the **Center for Government & Civic Service (CGCS)** at Austin Community College. Built on LangGraph with a router pattern that dispatches 8 capability subgraphs through a single Claude-powered state machine.

## Architecture

```
START → route_task → conditional routing
         ├── event_intake   → validate → eligibility → pricing → room → draft → END
         ├── email_triage   → classify → draft_reply → check_auto_send → END
         ├── calendar_check → check_availability → END
         ├── calendar_hold  → validate_hold → create_hold → END
         ├── pet_tracker    → read_sheet → (update?) prepare_update → END
         ├── event_lead     → assign_lead → schedule_reminders → END
         ├── reminder_check → find_due → send_reminders → END
         └── daily_digest   → build_digest → END
```

All runs traced via LangSmith. Every capability follows human-in-the-loop: no email reaches a requester without admin approval (except auto-send allowlist).

## Stack

| Layer | Technology |
|-------|-----------|
| AI | Claude Sonnet 4 via LangChain Anthropic |
| Agent Framework | LangGraph 0.3 (StateGraph) |
| API | FastAPI 0.115 |
| Database | PostgreSQL 16 + asyncpg |
| Orchestration | N8N workflows |
| External APIs | Google Calendar, Google Sheets, Zoho Mail |
| Observability | LangSmith tracing |
| Proxy | Caddy (auto-HTTPS) |
| Container | Docker Compose (4 services) |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Anthropic API key
- Google service account JSON (for Calendar & Sheets)
- Zoho Mail API token

### Setup

```bash
# Clone
git clone https://github.com/austinwells-pixel/cgcs-automation.git
cd cgcs-automation

# Configure
cp .env.example .env
# Edit .env with your API keys and secrets

# Start
docker compose up -d
```

The agent will be available at `http://localhost:8000`. N8N dashboard at `http://localhost:5678`.

### Run Tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r langgraph-agent/requirements.txt
pip install pytest pytest-asyncio pytest-mock

PYTHONPATH=langgraph-agent \
  ANTHROPIC_API_KEY=test-key \
  DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test \
  python -m pytest tests/ -v
```

221 tests passing.

## API Reference

### Authentication

- **Webhook Secret**: `X-Webhook-Secret` header — for N8N/public intake endpoints
- **API Key**: `Authorization: Bearer {LANGGRAPH_API_KEY}` — for admin/internal endpoints

### Endpoints (38 total)

#### Core Intake & Admin

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/health` | None | Health check |
| `POST` | `/api/v1/acknowledge` | Webhook | Send auto-acknowledgment email |
| `POST` | `/api/v1/evaluate` | Webhook | Process event intake through full pipeline |
| `POST` | `/api/v1/approve/{request_id}` | API Key | Admin approve/reject reservation |
| `GET` | `/api/v1/reservation/{request_id}` | API Key | Lookup reservation details |
| `POST` | `/api/v1/reservation/{request_id}/complete` | API Key | Mark reservation completed with actuals |
| `GET` | `/api/v1/staff-roster` | API Key | Current staff roster |
| `GET` | `/api/v1/dead-letter` | API Key | List failed requests |
| `POST` | `/api/v1/dead-letter/{id}/resolve` | API Key | Resolve DLQ entry |

#### Email Triage & Self-Improving Drafts

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/v1/email/triage` | Webhook | Classify email, draft reply, check auto-send |
| `POST` | `/api/v1/email/approve/{email_id}` | API Key | Approve/reject email draft |
| `GET` | `/api/v1/email/pending` | API Key | List pending email drafts |
| `POST` | `/api/v1/email/reject-and-rework/{email_id}` | API Key | Reject draft and generate 3 improved versions |
| `POST` | `/api/v1/email/select-revision/{pattern_id}` | API Key | Select a revision or provide custom draft |
| `GET` | `/api/v1/email/rejection-insights` | API Key | Rejection analytics and improvement rate |

#### Calendar Operations

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/v1/calendar/check` | Webhook | Check Google Calendar availability |
| `POST` | `/api/v1/calendar/hold` | API Key | Create calendar hold |

#### P.E.T. Tracker

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/v1/pet/query` | API Key | Query P.E.T. tracker spreadsheet |
| `POST` | `/api/v1/pet/update` | API Key | Stage P.E.T. update for approval |
| `POST` | `/api/v1/pet/update/{id}/approve` | API Key | Apply staged P.E.T. update |

#### Event Leads & Reminders

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/v1/leads/assign` | API Key | Assign event lead + schedule reminders |
| `GET` | `/api/v1/leads/{reservation_id}` | API Key | Get lead for event |
| `POST` | `/api/v1/reminders/check` | Webhook | Find and process due reminders |
| `POST` | `/api/v1/daily-digest` | Webhook | Generate admin daily digest (9 sections) |

#### Compliance Checklist

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/checklist/{request_id}` | API Key | Get checklist for reservation |
| `POST` | `/api/v1/checklist/{request_id}/bulk-update` | API Key | Bulk update checklist items |
| `POST` | `/api/v1/checklist/{request_id}/{item_key}` | API Key | Update single checklist item |

#### Dynamic Quote Versioning

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/api/v1/quote/generate/{request_id}` | API Key | Generate initial quote (v1) |
| `POST` | `/api/v1/quote/update/{request_id}` | API Key | Add/remove services, create new version |
| `GET` | `/api/v1/quote/history/{request_id}` | API Key | All quote versions for a reservation |
| `GET` | `/api/v1/quote/latest/{request_id}` | API Key | Latest quote version |

#### Reports & Analytics

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/reports/revenue` | API Key | Revenue aggregation report |
| `GET` | `/api/v1/reports/conversion-funnel` | API Key | Reservation conversion funnel |
| `GET` | `/api/v1/reports/export` | API Key | CSV export of reservations |
| `GET` | `/api/v1/reports/top-organizations` | API Key | Top organizations by booking count |
| `GET` | `/api/v1/reports/compliance` | API Key | Compliance on-time rates and overdue items |
| `GET` | `/api/v1/reports/process-insights` | API Key | Full process insights with AI recommendations |
| `POST` | `/api/v1/reports/generate-quarterly` | API Key | Generate quarterly report, optionally email |

## Features

### 1. Event Intake Pipeline

Processes reservation requests through eligibility evaluation, pricing classification, room setup, and draft response generation. Supports 5 pricing tiers (ACC internal, government, nonprofit, community partner, external) plus AMI facility pricing for paid events.

### 2. Email Triage

Classifies incoming emails into 11 categories with priority levels. Auto-detects Ad Astra receipts, calendar invites, and VIP senders. Drafts contextual replies with auto-send for allowlisted staff.

### 3. Automatic Acknowledgment Emails

Sends an immediate "Thank you — request received" email when a new event request arrives. Personalized with requester's first name and references the 3 business day response commitment.

### 4. Calendar Operations

Checks availability on the CGCS Events Google Calendar and creates hold events with the full CGCS calendar entry template. Supports event type prefixes: `HOLD`, `S-EVENT`, `C-EVENT`, `A-EVENT`.

### 5. P.E.T. Tracker

Reads from and stages updates to the P.E.T. tracking Google Sheet. All updates require admin approval before applying. Tracks 20 columns from Event Name through CGCS Labor.

### 6. Event Leads & Reminders

Assigns staff from the 8-person CGCS roster as event leads. Validates against the roster and enforces a 3-leads-per-staff-per-month cap. Auto-schedules reminders at 30, 14, 7, and 2 days before the event.

### 7. Revenue Tracking

Records actual revenue and attendance when events complete. Reports by period (week/month/quarter/year) with breakdowns by event type. CSV export and top organizations ranking.

### 8. Compliance Checklist

Auto-generates a 10-item event checklist on approval (user agreement, furniture layout, catering, run of show, walkthrough, TDX AV, payment, police, insurance, parking). Conditional items based on event type, time, and pricing tier. Business-day deadline calculation. Compliance report with on-time rates.

### 9. Self-Improving Email Drafts

When an admin rejects an AI-drafted email, the system generates 3 improved versions (Conservative, Moderate, Bold). Stores rejection patterns and feeds lessons back into future email drafting prompts, improving quality over time.

### 10. Dynamic Quote Versioning

Versioned line-item quotes that track pricing changes as event requirements evolve. Auto-generates initial quote on intake approval. Supports add/remove services with diff tracking. Integrates quotes into approval email drafts. 11 service types with AMI add-on pricing.

### 11. Process Insights & Quarterly Reports

Analytics layer across all operational data: email rejection rates and trends, quote revision metrics, intake turnaround times, compliance on-time rates, conversion funnels. Claude-powered actionable recommendations. Daily digest includes monthly quick stats (Section 9).

### 12. Daily Digest

Generates an 8am CT summary email for admin with 9 sections: pending approvals, new intakes, upcoming events (next 30 days), due reminders, pending user agreements, overdue deadlines, checklist items due this week, deadline reference, and monthly quick stats.

## Database

PostgreSQL with 11 tables under the `cgcs` schema:

| Table | Migration | Purpose |
|-------|-----------|---------|
| `reservations` | 001 | Event space reservations with full lifecycle + revenue actuals |
| `audit_trail` | 001 | Activity log for all task types |
| `dead_letter_queue` | 001 | Failed request recovery |
| `email_tasks` | 003 | Email triage records |
| `event_leads` | 003 | Staff lead assignments (one per event) |
| `event_reminders` | 003 | Scheduled reminders at 30d/14d/7d/48h |
| `calendar_holds` | 003 | Tentative calendar reservations |
| `pet_staged_updates` | 003 | Staged P.E.T. updates awaiting approval |
| `event_checklist` | 007 | Compliance checklist items with deadlines |
| `email_rejection_patterns` | 008 | Email draft rejection history and revisions |
| `quote_versions` | 009 | Versioned line-item quotes per reservation |

Migrations in `db/migrations/` (001–003, 005, 007–009). Applied automatically on container start.

## N8N Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `event-space-intake.json` | Webhook | Form submission → calendar check → agent evaluation → admin notification |
| `admin-approval.json` | Webhook | Admin approve/reject → send email to requester |
| `email-monitoring.json` | Cron (5 min) | Poll Zoho Mail → triage via agent → route to admin |
| `calendar-hold.json` | Manual | Admin creates calendar hold |
| `reminder-cron.json` | Cron (8am CT) | Check due reminders + generate daily digest |

## Project Structure

```
ai-intake/
├── langgraph-agent/
│   └── app/
│       ├── main.py                 # FastAPI application (38 endpoints)
│       ├── config.py               # Pydantic settings
│       ├── models.py               # Request/response models (40+ models)
│       ├── cgcs_constants.py       # Staff roster, pricing, deadlines, templates, checklist
│       ├── prompt_tuning.py        # Self-improving prompt lessons
│       ├── graph/
│       │   ├── state.py            # AgentState TypedDict
│       │   ├── builder.py          # Graph construction
│       │   ├── edges.py            # Conditional routing
│       │   └── nodes/
│       │       ├── router.py       # Task type routing
│       │       ├── intake.py       # Event intake (7 nodes)
│       │       ├── email_triage.py # Email classification (3 nodes)
│       │       ├── calendar.py     # Availability check
│       │       ├── calendar_hold.py# Hold creation
│       │       ├── pet_tracker.py  # P.E.T. operations
│       │       ├── event_lead.py   # Lead assignment
│       │       ├── reminders.py    # Reminder processing
│       │       ├── daily_digest.py # Admin digest (9 sections)
│       │       └── shared.py       # LLM utilities
│       ├── services/
│       │   ├── quote_builder.py    # Pure-function quote generation
│       │   ├── process_insights.py # Analytics & recommendations
│       │   ├── google_calendar.py  # Calendar API
│       │   ├── google_sheets.py    # Sheets API
│       │   └── zoho_mail.py        # Zoho Mail API
│       ├── db/
│       │   ├── connection.py       # asyncpg pool
│       │   ├── queries.py          # Core reservation queries
│       │   ├── email_queries.py    # Email task queries
│       │   ├── checklist_queries.py# Compliance checklist queries
│       │   ├── rejection_queries.py# Email rejection pattern queries
│       │   ├── quote_queries.py    # Quote version queries
│       │   └── report_queries.py   # Revenue & reporting queries
│       ├── prompts/                # Claude system prompts
│       └── data/                   # Pricing tiers, room configs
├── db/migrations/                  # PostgreSQL migrations (7 files)
├── n8n/workflows/                  # N8N workflow JSON
├── caddy/                          # Reverse proxy config
├── tests/                          # 221 tests
│   ├── test_api.py                 # Core endpoint tests
│   ├── test_graph.py               # Graph node & routing tests
│   ├── test_email_triage.py        # Email classification tests
│   ├── test_calendar.py            # Calendar operation tests
│   ├── test_leads.py               # Event lead & reminder tests
│   ├── test_acknowledgment.py      # Acknowledgment email tests
│   ├── test_checklist.py           # Compliance checklist tests
│   ├── test_reports.py             # Revenue & reporting tests
│   ├── test_rejection.py           # Self-improving email tests
│   ├── test_quotes.py              # Quote versioning tests
│   ├── test_process_insights.py    # Process insights tests
│   └── conftest.py                 # Shared fixtures
├── docker-compose.yml
└── .env.example
```

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `WEBHOOK_SECRET` | Yes | Shared secret for N8N webhooks |
| `LANGGRAPH_API_KEY` | Yes | API key for admin endpoints |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | For calendar/sheets | Path to service account JSON |
| `ZOHO_MAIL_TOKEN` | For email | Zoho Mail API token |
| `LANGCHAIN_API_KEY` | Optional | LangSmith tracing |

## Key Design Decisions

- **Human-in-the-loop**: No outbound email without admin approval (except allowlist)
- **Dead letter queue**: Failed graph executions are never silently dropped
- **Retry with backoff**: All LLM and HTTP calls retry 3x with exponential backoff
- **Input sanitization**: All user inputs stripped of control characters and truncated
- **Single state machine**: One `AgentState` TypedDict carries all data through the graph
- **continueOnFail**: Non-critical operations (auto-quote, monthly stats) never block main flow
- **Pure functions**: Quote builder has zero DB/async dependencies for easy unit testing
- **Self-improving prompts**: Email rejection patterns fed back into future drafting
- **Backward compatibility**: `ReservationState = AgentState` alias preserves existing imports
