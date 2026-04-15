# CGCS Unified Agent

AI-powered automation engine for the **Center for Government & Civic Service (CGCS)** at Austin Community College. Built on LangGraph with a router pattern that dispatches 10 capability subgraphs through a single Claude-powered state machine.

## Architecture

```
START → route_task → conditional routing
         ├── event_intake       → validate → eligibility → pricing → room → draft → END
         ├── email_triage       → classify → draft_reply → check_auto_send → END
         ├── smartsheet_intake  → classify_request → draft_emails → END
         ├── email_reply        → edit_loop → escalation → furniture/AV detect → END
         ├── calendar_check     → check_availability → END
         ├── calendar_hold      → validate_hold → create_hold → END
         ├── pet_tracker        → read_sheet → (update?) prepare_update → END
         ├── event_lead         → assign_lead → schedule_reminders → END
         ├── reminder_check     → find_due → send_reminders → END
         └── daily_digest       → build_digest (11 sections) → END
```

All runs traced via LangSmith. Every capability follows human-in-the-loop: no email reaches a requester without admin approval (except auto-send allowlist and easy-tier auto-replies).

### Smartsheet Intake Pipeline

```
Smartsheet email arrives (automations@app.smartsheet.com)
  → N8N detects via Gmail API
  → POST /webhook/smartsheet-new-entry
  → Parse email fields (40+ fields extracted)
  → 14 business day lead time check
  → Classify: Easy / Mid / Hard
  → Auto-ack email to requester
  → Create P.E.T. spreadsheet row (20 columns)
  → Create HOLD on Google Calendar (30+ field description)
  → Draft response email
  → If furniture: draft furniture email to Moving Team
  → If weekend/evening: draft police email to Officer Ortiz
  → Easy: auto-send | Mid/Hard: queue for Austin's approval
```

### Email Reply Processing

```
Client replies to event thread
  → N8N detects via Gmail API
  → POST /webhook/email-reply
  → Increment edit loop (max 10 replies)
  → Detect escalation (human request / frustration / 3+ failed)
  → Detect furniture changes → draft updated Moving Team email
  → Detect AV/catering changes → create dashboard alert
  → Draft response → queue for approval
```

## Stack

| Layer | Technology |
|-------|-----------|
| AI | Claude Sonnet 4 via LangChain Anthropic |
| Agent Framework | LangGraph 0.3 (StateGraph) |
| API | FastAPI 0.115 |
| Database | PostgreSQL 16 + asyncpg |
| Email | Gmail API (service account + domain-wide delegation) |
| Orchestration | N8N workflows |
| External APIs | Google Calendar, Google Sheets, Gmail |
| Observability | LangSmith tracing |
| Proxy | Caddy (auto-HTTPS) |
| Container | Docker Compose (4 services) |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Anthropic API key
- Google service account JSON (for Calendar, Sheets, Gmail)
- Domain-wide delegation configured for admin@cgcs-acc.org

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

### Deployment (Coolify)

Target deployment: Coolify on a self-hosted VPS.

- **Docker Compose** deployment via Coolify's compose support
- **Environment variables** configured in Coolify dashboard (secrets panel)
- **Google service account JSON** mounted as a volume or injected via Coolify's file mount
- **Caddy** handles auto-HTTPS via Coolify's built-in proxy, or use Coolify's Traefik
- **PostgreSQL** can use Coolify's managed Postgres or an external instance
- **N8N** deployed as a separate Coolify service with its own subdomain

## API Reference

### Authentication

- **Webhook Secret**: `X-Webhook-Secret` header — for N8N/public intake endpoints
- **API Key**: `Authorization: Bearer {LANGGRAPH_API_KEY}` — for admin/internal endpoints

### Endpoints (46 total)

#### N8N Webhook Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/webhook/smartsheet-new-entry` | Webhook | Full Smartsheet intake pipeline |
| `POST` | `/webhook/email-reply` | Webhook | Process reply in event thread |
| `POST` | `/webhook/admin-response` | Webhook | Admin approve/reject/edit draft |
| `POST` | `/webhook/police-confirmed` | Webhook | Police coverage confirmation |

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
| `POST` | `/api/v1/daily-digest` | Webhook | Generate admin daily digest (11 sections) |

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

#### Dashboard Alerts

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/alerts/active` | API Key | List active dashboard alerts |
| `POST` | `/api/v1/alerts/{id}/dismiss` | API Key | Dismiss an alert |

## Database

PostgreSQL with 12 tables under the `cgcs` schema:

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
| `dashboard_alerts` | 010 | AV/catering change alerts and pipeline errors |

Migrations in `db/migrations/` (001-003, 005, 007-010). Applied automatically on container start.

## N8N Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `event-space-intake.json` | Webhook | Form submission → calendar check → agent evaluation → admin notification |
| `admin-approval.json` | Webhook | Admin approve/reject → send email to requester |
| `email-monitoring.json` | Cron (5 min) | Poll Gmail → triage via agent → route to admin |
| `smartsheet-intake.json` | Gmail trigger | Smartsheet email → parse → 14-day check → full pipeline |
| `email-reply.json` | Gmail trigger | Thread reply → edit loop → escalation → change detection |
| `calendar-hold.json` | Manual | Admin creates calendar hold |
| `reminder-cron.json` | Cron (8am CT) | Check due reminders + generate daily digest |

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `WEBHOOK_SECRET` | Yes | Shared secret for N8N webhooks |
| `LANGGRAPH_API_KEY` | Yes | API key for admin endpoints |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Yes | Path to service account JSON |
| `GMAIL_DELEGATED_USER` | Yes | Gmail address to impersonate (admin@cgcs-acc.org) |
| `GOOGLE_CALENDAR_ID` | For calendar | CGCS Events calendar ID |
| `PET_TRACKER_SPREADSHEET_ID` | For P.E.T. | Google Sheets spreadsheet ID |
| `LANGCHAIN_API_KEY` | Optional | LangSmith tracing |

## Key Design Decisions

- **Human-in-the-loop**: No outbound email without admin approval (except allowlist and easy auto-replies)
- **Dead letter queue**: Failed graph executions are never silently dropped
- **Dashboard alerts**: AV/catering changes create alerts instead of auto-drafting emails
- **Edit loop cap**: Threads are limited to 10 back-and-forth replies before human handoff
- **Escalation detection**: Frustration language and explicit human requests auto-forward to admin team
- **Retry with backoff**: All LLM and HTTP calls retry 3x with exponential backoff
- **Error classification**: Errors classified as retryable (timeout/rate-limit) vs fatal (validation/missing data)
- **Input sanitization**: All user inputs stripped of control characters and truncated
- **Single state machine**: One `AgentState` TypedDict carries all data through the graph
- **continueOnFail**: Non-critical operations (auto-quote, monthly stats) never block main flow
- **Pure functions**: Quote builder, intake processor, classifier have zero DB/async dependencies
- **Self-improving prompts**: Email rejection patterns fed back into future drafting
- **Gmail API**: Domain-wide delegation via service account replaces Zoho Mail
- **Backward compatibility**: `ReservationState = AgentState` alias preserves existing imports
