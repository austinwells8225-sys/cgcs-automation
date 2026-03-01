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

96 tests passing.

## API Reference

### Authentication

- **Webhook Secret**: `X-Webhook-Secret` header — for N8N/public intake endpoints
- **API Key**: `Authorization: Bearer {LANGGRAPH_API_KEY}` — for admin/internal endpoints

### Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/health` | None | Health check |
| `POST` | `/api/v1/evaluate` | Webhook | Process event intake through full pipeline |
| `POST` | `/api/v1/approve/{request_id}` | API Key | Admin approve/reject reservation |
| `GET` | `/api/v1/reservation/{request_id}` | API Key | Lookup reservation details |
| `POST` | `/api/v1/email/triage` | Webhook | Classify email, draft reply, check auto-send |
| `POST` | `/api/v1/email/approve/{email_id}` | API Key | Approve/reject email draft |
| `GET` | `/api/v1/email/pending` | API Key | List pending email drafts |
| `POST` | `/api/v1/calendar/check` | Webhook | Check Google Calendar availability |
| `POST` | `/api/v1/calendar/hold` | API Key | Create calendar hold |
| `POST` | `/api/v1/pet/query` | API Key | Query P.E.T. tracker spreadsheet |
| `POST` | `/api/v1/pet/update` | API Key | Stage P.E.T. update for approval |
| `POST` | `/api/v1/pet/update/{id}/approve` | API Key | Apply staged P.E.T. update |
| `POST` | `/api/v1/leads/assign` | API Key | Assign event lead + schedule reminders |
| `GET` | `/api/v1/leads/{reservation_id}` | API Key | Get lead for event |
| `POST` | `/api/v1/reminders/check` | Webhook | Find and process due reminders |
| `POST` | `/api/v1/daily-digest` | Webhook | Generate admin daily digest |
| `GET` | `/api/v1/staff-roster` | API Key | Current staff roster |
| `GET` | `/api/v1/dead-letter` | API Key | List failed requests |
| `POST` | `/api/v1/dead-letter/{id}/resolve` | API Key | Resolve DLQ entry |

## Capabilities

### Event Intake

Processes reservation requests through eligibility evaluation, pricing classification, room setup, and draft response generation. Supports 5 pricing tiers (ACC internal, government, nonprofit, community partner, external) plus AMI facility pricing for paid events.

### Email Triage

Classifies incoming emails into 11 categories with priority levels. Auto-detects Ad Astra receipts (marks read, only surfaces approvals), calendar invites (leaves for manual handling), and VIP senders (auto-boosts to high priority). Drafts contextual replies.

### Calendar Operations

Checks availability on the CGCS Events Google Calendar and creates hold events with the full CGCS calendar entry template. Supports event type prefixes: `HOLD`, `S-EVENT`, `C-EVENT`, `A-EVENT`.

### P.E.T. Tracker

Reads from and stages updates to the P.E.T. tracking Google Sheet. All updates require admin approval before applying. Tracks 20 columns from Event Name through CGCS Labor.

### Event Leads

Assigns staff from the 8-person CGCS roster as event leads. Validates against the roster and enforces a 3-leads-per-staff-per-month cap. Auto-schedules reminders at 30, 14, 7, and 2 days before the event.

### Daily Digest

Generates an 8am CT summary email for admin with pending approvals, new intakes, upcoming events (next 30 days), due reminders, pending user agreements, and overdue deadline warnings.

## Database

PostgreSQL with 8 tables under the `cgcs` schema:

- `reservations` — Event space reservations with full lifecycle
- `audit_trail` — Activity log for all task types
- `email_tasks` — Email triage records
- `event_leads` — Staff lead assignments (one per event)
- `event_reminders` — Scheduled reminders at 30d/14d/7d/48h
- `calendar_holds` — Tentative calendar reservations
- `pet_staged_updates` — Staged P.E.T. updates awaiting approval
- `dead_letter_queue` — Failed request recovery

Migrations in `db/migrations/`. Applied automatically on container start.

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
│       ├── main.py                 # FastAPI application (19 endpoints)
│       ├── config.py               # Pydantic settings
│       ├── models.py               # Request/response models
│       ├── cgcs_constants.py       # Staff roster, pricing, deadlines, templates
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
│       │       ├── daily_digest.py # Admin digest
│       │       └── shared.py       # LLM utilities
│       ├── services/               # Google Calendar, Sheets, Zoho Mail
│       ├── db/                     # asyncpg queries
│       ├── prompts/                # Claude system prompts
│       └── memories/               # Email triage rules
├── db/migrations/                  # PostgreSQL migrations
├── n8n/workflows/                  # N8N workflow JSON
├── caddy/                          # Reverse proxy config
├── tests/                          # 96 tests
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
- **Backward compatibility**: `ReservationState = AgentState` alias preserves existing imports
