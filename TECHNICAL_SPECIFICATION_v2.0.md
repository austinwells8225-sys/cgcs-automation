# CGCS Unified Agent -- Technical Specification

**Version:** 2.0
**Date:** 2026-03-03
**System:** CGCS Event Space Automation Engine
**Organization:** Center for Government & Civic Service (CGCS), Austin Community College
**Admin:** Austin Wells, Strategic Planner for Community Relations & Environmental Affairs

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Architecture](#3-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Project Structure](#5-project-structure)
6. [State Machine & Graph Engine](#6-state-machine--graph-engine)
7. [Capability Specifications](#7-capability-specifications)
8. [API Specification](#8-api-specification)
9. [Database Schema](#9-database-schema)
10. [External Service Integrations](#10-external-service-integrations)
11. [Authentication & Authorization](#11-authentication--authorization)
12. [Human-in-the-Loop Architecture](#12-human-in-the-loop-architecture)
13. [Business Rules & Constants](#13-business-rules--constants)
14. [Prompt Engineering](#14-prompt-engineering)
15. [Error Handling & Resilience](#15-error-handling--resilience)
16. [Security Architecture](#16-security-architecture)
17. [Deployment & Infrastructure](#17-deployment--infrastructure)
18. [Observability & Monitoring](#18-observability--monitoring)
19. [Testing & Evaluation](#19-testing--evaluation)
20. [Configuration Reference](#20-configuration-reference)
21. [Data Flow Diagrams](#21-data-flow-diagrams)
22. [Roadmap — v3.0 Architecture](#22-roadmap--v30-architecture)
23. [Appendices](#appendices)

---

## 1. Executive Summary

The CGCS Unified Agent is a production-grade AI automation platform for the Center for Government & Civic Service at Austin Community College. Built on LangGraph, it is a unified state machine that routes **12 distinct AI-powered capabilities** through a single FastAPI application backed by Claude (Anthropic).

The system processes event space reservations, email triage (with self-improving drafts), calendar management, event lead assignments, reminders, P.E.T. tracking, compliance checklists, revenue tracking, dynamic quote versioning, process insights with AI-powered recommendations, and daily digests — all with **human-in-the-loop approval gates** ensuring no outbound communication reaches external parties without explicit admin approval.

### Key Metrics

| Metric | v1.0 | v2.0 |
|--------|------|------|
| Capability subgraphs | 8 | 12 |
| FastAPI endpoints | 19 | 38 |
| PostgreSQL tables | 8 | 11 |
| Migrations | 3 | 9 (001–009) |
| Test suite | 96 | 228 passing tests |
| AgentState fields | 82 | 90+ |
| Pydantic request/response models | 16 | 40+ |
| LLM system prompts | 5 | 8 |
| Services modules | 3 | 5 |
| Database query modules | 6 | 9 |

### What Changed from v1.0 to v2.0

| Area | Change |
|------|--------|
| **Capabilities** | Added: acknowledgment emails, compliance checklists, revenue tracking, self-improving email drafts, dynamic quote versioning, process insights & quarterly reports |
| **Architecture intent** | N8N repositioned from admin UI to webhook orchestration only; LangSmith + CGCS Command dashboard designated as the human-in-the-loop interfaces |
| **Labor rates** | Added LABOR_RATES constant with director ($66/hr) and intern ($25/hr) tiers |
| **Daily digest** | Expanded from 7 sections to 9 sections (added checklist items due, monthly quick stats) |
| **AI recommendations** | Process insights layer calls Claude to generate actionable recommendations from operational data |
| **Quote system** | Versioned line-item quotes with diff tracking, auto-generated on intake approval |
| **Self-improving prompts** | Rejection patterns feed lessons back into future email drafting |

---

## 2. System Overview

### 2.1 Purpose

The CGCS manages event space at Austin Community College's facilities. Prior to this system, all intake processing — eligibility evaluation, pricing, calendar checks, email responses, and operational tracking — was performed manually by the CGCS administrator. This system automates those workflows while preserving human oversight at critical decision points.

### 2.2 Core Principles

1. **Human-in-the-loop**: No outbound email reaches a requester without admin approval (except for an explicit auto-send allowlist of 2 internal staff members).
2. **Never drop a request**: Failed graph executions are captured in a dead letter queue for manual recovery. No request is ever silently lost.
3. **Retry resilience**: All LLM calls and external HTTP requests retry 3x with exponential backoff.
4. **Input sanitization**: All user-supplied strings are stripped of control characters, collapsed of excessive whitespace, and truncated to 5,000 characters.
5. **Single state machine**: One `AgentState` TypedDict carries all data through the graph, with task_type-based routing selecting the correct subgraph.
6. **Auditability**: Every state transition and admin action is logged to an audit trail with actor identity and JSONB details.
7. **continueOnFail**: Non-critical operations (auto-quote generation, monthly stats) never block the main flow. Failures are logged but execution continues.
8. **Self-improving**: Rejection patterns are stored and fed back into future prompts, so the system learns from admin corrections over time.

### 2.3 Users

| Role | Description | Authentication |
|------|-------------|---------------|
| External Requester | Submits event space reservation requests via web form | None (form processed by N8N) |
| CGCS Admin | Reviews, approves/rejects reservations and email drafts | CGCS Command dashboard (API key) / LangSmith (LangSmith API key) |
| N8N Webhooks | Automated orchestration workflows (triggers only) | Webhook shared secret |
| Internal API Consumers | Admin endpoints for lead assignment, P.E.T. tracker, etc. | Bearer API key |

---

## 3. Architecture

### 3.1 High-Level Architecture

```
                          Internet
                             |
                         [Caddy]
                    (auto-HTTPS reverse proxy)
                       /          \
                [N8N:5678]    [Agent:8000]
               (triggers only)     |
                     |             +---> [LangSmith] (observability + HITL)
                     +------+------+
                            |
                      [PostgreSQL:5432]
                            |
                      [cgcs schema]
```

### 3.2 Component Architecture

```
FastAPI Application (app/main.py)
    |
    +-- 38 API Endpoints
    |     |- Health (unauthenticated)
    |     |- Event Intake (webhook secret auth)
    |     |- Acknowledgment (webhook secret auth)
    |     |- Admin Approval (API key auth)
    |     |- Reservation Completion (API key auth)
    |     |- Email Triage (webhook secret auth)
    |     |- Email Rejection & Rework (API key auth)
    |     |- Calendar Operations (mixed auth)
    |     |- P.E.T. Tracker (API key auth)
    |     |- Event Leads (API key auth)
    |     |- Reminders (webhook secret auth)
    |     |- Daily Digest (webhook secret auth)
    |     |- Compliance Checklist (API key auth)
    |     |- Dynamic Quotes (API key auth)
    |     |- Revenue & Reports (API key auth)
    |     |- Process Insights (API key auth)
    |     |- Dead Letter Queue (API key auth)
    |     +- Staff Roster (API key auth)
    |
    +-- LangGraph State Machine (graph/)
    |     |- StateGraph(AgentState)
    |     |- 21+ Nodes across 11 modules
    |     |- 7 Conditional Edge Functions
    |     +- Router pattern: route_task -> subgraph
    |
    +-- Services (services/)
    |     |- Google Calendar API
    |     |- Google Sheets API
    |     |- Zoho Mail API
    |     |- Quote Builder (pure functions)
    |     +- Process Insights (analytics layer)
    |
    +-- Database Layer (db/)
    |     |- asyncpg connection pool (2-10 connections)
    |     |- 9 query modules
    |     +- PostgreSQL 16 with cgcs schema (11 tables)
    |
    +-- Business Logic
    |     |- data/ — Pricing tiers, room configs, eligibility
    |     |- cgcs_constants.py — Staff, deadlines, labor rates, templates
    |     +- prompt_tuning.py — Self-improving prompt lessons
    |
    +-- Prompt Templates (prompts/)
          |- Eligibility evaluation
          |- Pricing classification
          |- Room setup parsing
          |- Approval/rejection email drafting
          |- Email triage classification
          |- Rejection rework system prompt
          |- Quote integration prompt
          +- Process recommendations prompt
```

### 3.3 Graph Architecture (State Machine)

```
START
  |
  v
[route_task] ---> conditional routing via after_routing()
  |
  |-- event_intake:
  |     validate_input -> evaluate_eligibility -> determine_pricing
  |       -> evaluate_room_setup -> draft_approval_response -> END
  |     (or) evaluate_eligibility -> draft_rejection -> END
  |     (on approval: auto-generate quote v1, send acknowledgment)
  |
  |-- email_triage:
  |     classify_email -> draft_email_reply -> check_auto_send -> END
  |     (rejection: store pattern, generate 3 improved versions)
  |
  |-- calendar_check:
  |     check_calendar_availability -> END
  |
  |-- calendar_hold:
  |     validate_hold_request -> create_calendar_hold -> END
  |
  |-- pet_tracker:
  |     read_pet_tracker -> (if update) prepare_pet_update -> END
  |                      -> (if read) END
  |
  |-- event_lead:
  |     assign_event_lead -> schedule_reminders -> END
  |
  |-- reminder_check:
  |     find_due_reminders -> send_reminders -> END
  |
  |-- daily_digest:
  |     build_daily_digest (9 sections) -> END
  |
  +-- (any errors) -> handle_error -> END
```

---

## 4. Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| AI Model | Claude Sonnet 4 | `claude-sonnet-4-20250514` | LLM for eligibility, pricing, email triage, drafting, recommendations |
| Agent Framework | LangGraph | 0.3.x | State machine graph execution |
| LLM Integration | LangChain Anthropic | 0.3.x | Claude API wrapper with message formatting |
| Web Framework | FastAPI | 0.115.x | REST API with automatic OpenAPI docs |
| ASGI Server | Uvicorn | 0.34.x | Production ASGI server (2 workers) |
| Database | PostgreSQL | 16-alpine | Primary data store |
| DB Driver | asyncpg | 0.30.x | Async PostgreSQL driver |
| Data Validation | Pydantic | 2.10.x | Request/response models, settings |
| Settings | pydantic-settings | 2.7.x | Environment-based configuration |
| HTTP Client | httpx | 0.28.x | External API calls (Google, Zoho) |
| Google Auth | google-auth | 2.x | Service account authentication |
| Observability | LangSmith | 0.2.x | LLM trace collection + human-in-the-loop review |
| Orchestration | N8N | latest | Webhook triggers and cron scheduling (5 workflows) |
| Reverse Proxy | Caddy | 2-alpine | Auto-HTTPS, IP restriction |
| Containerization | Docker Compose | - | 4-service deployment |
| Runtime | Python | 3.12-slim | Application runtime |

### 4.1 Python Dependencies (requirements.txt)

```
fastapi>=0.115,<0.116
uvicorn[standard]>=0.34,<0.35
langgraph>=0.3,<0.4
langchain-anthropic>=0.3,<0.4
psycopg[binary]>=3.2,<4
asyncpg>=0.30,<0.31
pydantic>=2.10,<3
pydantic-settings>=2.7,<3
email-validator>=2.0,<3
httpx>=0.28,<0.29
python-dotenv>=1.0,<2
langsmith>=0.2,<1
google-auth>=2.0,<3
```

---

## 5. Project Structure

```
ai-intake/
├── langgraph-agent/
│   ├── Dockerfile                          # Python 3.12-slim, non-root user
│   ├── requirements.txt                    # Pinned dependency ranges
│   └── app/
│       ├── main.py                         # FastAPI app, 38 endpoints, lifespan mgmt
│       ├── config.py                       # Pydantic Settings (26+ env vars)
│       ├── models.py                       # 40+ Pydantic request/response models
│       ├── cgcs_constants.py               # Staff roster, pricing, deadlines, labor rates, templates, checklist
│       ├── prompt_tuning.py                # Self-improving prompt lessons from rejection patterns
│       ├── graph/
│       │   ├── state.py                    # AgentState TypedDict (90+ fields)
│       │   ├── builder.py                  # StateGraph construction (21+ nodes)
│       │   ├── edges.py                    # 7 conditional routing functions
│       │   └── nodes/
│       │       ├── __init__.py             # Re-exports all node functions
│       │       ├── router.py               # Task-type validation & routing
│       │       ├── intake.py               # Event intake: validate, eligibility, pricing, room, draft (7 nodes)
│       │       ├── email_triage.py         # Email: classify, draft, auto-send (3 nodes)
│       │       ├── calendar.py             # Calendar availability check (1 node)
│       │       ├── calendar_hold.py        # Calendar hold: validate, create (2 nodes)
│       │       ├── pet_tracker.py          # P.E.T.: read, prepare update (2 nodes)
│       │       ├── event_lead.py           # Event leads: assign, schedule reminders (2 nodes)
│       │       ├── reminders.py            # Reminders: find due, send (2 nodes)
│       │       ├── daily_digest.py         # Daily digest builder (1 node, 9 sections)
│       │       └── shared.py              # LLM client, retry logic, sanitization
│       ├── services/
│       │   ├── google_calendar.py          # Google Calendar API (check, create hold)
│       │   ├── google_sheets.py            # Google Sheets API (read, stage, apply)
│       │   ├── zoho_mail.py               # Zoho Mail API (fetch unread, send)
│       │   ├── quote_builder.py           # Pure-function quote generation (zero DB deps)
│       │   └── process_insights.py        # Analytics queries & AI recommendations
│       ├── db/
│       │   ├── connection.py               # asyncpg pool management (2-10 connections)
│       │   ├── queries.py                  # Reservation CRUD, audit trail, DLQ
│       │   ├── email_queries.py            # Email task CRUD
│       │   ├── lead_queries.py             # Event lead & reminder CRUD
│       │   ├── hold_queries.py             # Calendar hold CRUD
│       │   ├── pet_queries.py             # P.E.T. staged update CRUD
│       │   ├── checklist_queries.py       # Compliance checklist CRUD & reports
│       │   ├── rejection_queries.py       # Email rejection pattern CRUD
│       │   ├── quote_queries.py           # Quote version CRUD
│       │   └── report_queries.py          # Revenue & reporting queries
│       ├── prompts/
│       │   └── templates.py               # 8 Claude system prompts
│       └── data/
│           ├── pricing.py                  # 5 pricing tiers, cost computation
│           ├── room_setup.py               # 5 room configs, auto-assignment
│           └── eligibility.py             # Eligibility rules & exclusions
├── db/
│   ├── init.sql                            # Schema bootstrap (CREATE SCHEMA cgcs)
│   └── migrations/
│       ├── 001_initial_schema.sql          # Core tables: reservations, audit, pricing, rooms, DLQ
│       ├── 002_seed_data.sql               # Pricing tiers & room configurations
│       ├── 003_multi_capability.sql        # Email, leads, reminders, holds, P.E.T. tables
│       ├── 004_placeholder.sql             # Reserved
│       ├── 005_revenue_columns.sql         # Revenue columns on reservations
│       ├── 006_placeholder.sql             # Reserved
│       ├── 007_event_checklist.sql         # Compliance checklist table
│       ├── 008_rejection_patterns.sql      # Email rejection patterns table
│       └── 009_quote_versions.sql          # Quote versioning table
├── caddy/
│   └── Caddyfile                           # Reverse proxy with IP restriction
├── tests/                                  # 228 tests
│   ├── conftest.py                         # Shared test fixtures
│   ├── test_api.py                         # Core endpoint tests
│   ├── test_graph.py                       # Graph node unit tests
│   ├── test_email_triage.py               # Email triage tests
│   ├── test_calendar.py                   # Calendar tests
│   ├── test_leads.py                      # Event lead tests
│   ├── test_acknowledgment.py             # Acknowledgment email tests
│   ├── test_checklist.py                  # Compliance checklist tests
│   ├── test_reports.py                    # Revenue & reporting tests
│   ├── test_rejection.py                  # Self-improving email tests
│   ├── test_quotes.py                     # Quote versioning tests
│   ├── test_process_insights.py           # Process insights & quarterly report tests
│   └── test_labor_rates.py               # Labor rate constant tests
├── docker-compose.yml                      # 4-service stack definition
├── .env.example                            # Environment variable template (26+ vars)
├── README.md                               # Project documentation
├── TECHNICAL_SPECIFICATION_v1.0.md         # Previous version (archived)
└── TECHNICAL_SPECIFICATION_v2.0.md         # This document
```

---

## 6. State Machine & Graph Engine

### 6.1 AgentState TypedDict

The entire system operates on a single TypedDict that carries all data through the graph. Fields are namespaced by capability using optional typing (`total=False`).

**File:** `langgraph-agent/app/graph/state.py`

| Field Group | Fields | Purpose |
|-------------|--------|---------|
| **Common** (7) | `task_type`, `request_id`, `errors`, `decision`, `draft_response`, `requires_approval`, `approved` | Routing, tracking, approval gate |
| **Event Intake** (16) | `requester_name`, `requester_email`, `requester_organization`, `event_name`, `event_description`, `requested_date`, `requested_start_time`, `requested_end_time`, `room_requested`, `estimated_attendees`, `setup_requirements_raw`, `calendar_available`, `is_eligible`, `eligibility_reason`, `pricing_tier`, `estimated_cost`, `room_assignment`, `setup_config` | Full reservation pipeline |
| **Email Triage** (8) | `email_id`, `email_from`, `email_subject`, `email_body`, `email_priority`, `email_category`, `email_draft_reply`, `email_auto_send` | Email classification & response |
| **Calendar Check** (5) | `calendar_query_date`, `calendar_query_start`, `calendar_query_end`, `calendar_is_available`, `calendar_events` | Availability queries |
| **Calendar Hold** (6) | `hold_org_name`, `hold_date`, `hold_start_time`, `hold_end_time`, `hold_event_id`, `hold_event_type` | Hold creation |
| **P.E.T. Tracker** (4) | `pet_operation`, `pet_row_data`, `pet_query`, `pet_result` | Spreadsheet operations |
| **Event Lead** (5) | `lead_staff_name`, `lead_staff_email`, `lead_reservation_id`, `lead_event_date`, `lead_current_month_count` | Staff assignment |
| **Reminders** (2) | `reminders_due`, `reminders_sent` | Notification scheduling |
| **Daily Digest** (7) | `digest_pending_approvals`, `digest_new_intakes`, `digest_upcoming_events`, `digest_pending_agreements`, `digest_overdue_deadlines`, `digest_checklist_items_due`, `digest_monthly_stats` | Admin summary (9 sections) |
| **Event Type** (1) | `event_type` | S-EVENT, C-EVENT, A-EVENT classification |

### 6.2 Graph Construction

**File:** `langgraph-agent/app/graph/builder.py`

The graph is built using LangGraph's `StateGraph` API with 21+ nodes and 7 conditional edge functions.

**Nodes (21+):**

| Node | Module | LLM Call | Description |
|------|--------|----------|-------------|
| `route_task` | router.py | No | Validates task_type, passes through |
| `validate_input` | intake.py | No | Pure Python field validation & sanitization |
| `evaluate_eligibility` | intake.py | Yes | Claude evaluates CGCS eligibility criteria |
| `determine_pricing` | intake.py | Yes | Claude classifies pricing tier |
| `evaluate_room_setup` | intake.py | Yes | Claude parses setup requirements |
| `draft_approval_response` | intake.py | Yes | Claude drafts approval email (with quote integration) |
| `draft_rejection` | intake.py | Yes | Claude drafts rejection email |
| `classify_email` | email_triage.py | Yes* | Claude classifies email priority/category |
| `draft_email_reply` | email_triage.py | Yes | Claude drafts contextual reply (with rejection lessons) |
| `check_auto_send` | email_triage.py | No | Checks sender against auto-send allowlist |
| `check_calendar_availability` | calendar.py | No | Google Calendar API query |
| `validate_hold_request` | calendar_hold.py | No | Pure Python hold field validation |
| `create_calendar_hold` | calendar_hold.py | No | Google Calendar API event creation |
| `read_pet_tracker` | pet_tracker.py | No | Google Sheets API read |
| `prepare_pet_update` | pet_tracker.py | No | Stages update for approval |
| `assign_event_lead` | event_lead.py | No | Validates staff roster & monthly cap |
| `schedule_reminders` | event_lead.py | No | Computes 30d/14d/7d/48h reminder dates |
| `find_due_reminders` | reminders.py | No | Filters reminders due today or overdue |
| `send_reminders` | reminders.py | No | Marks reminders as sent |
| `build_daily_digest` | daily_digest.py | No | Assembles 9-section digest email |
| `handle_error` | intake.py | No | Generates fallback manual review response |

*Ad Astra and calendar invite detection is pure Python; standard emails use LLM.

### 6.3 Conditional Edge Functions (7)

**File:** `langgraph-agent/app/graph/edges.py`

| Function | Source Node | Conditions | Targets |
|----------|-------------|------------|---------|
| `after_routing` | route_task | 8 task_type mappings + error check | validate_input, classify_email, check_calendar_availability, validate_hold_request, read_pet_tracker, assign_event_lead, find_due_reminders, build_daily_digest, handle_error |
| `after_validation` | validate_input | errors present? | handle_error or evaluate_eligibility |
| `after_eligibility` | evaluate_eligibility | decision=needs_review / not eligible / eligible | handle_error, draft_rejection, determine_pricing |
| `after_email_classification` | classify_email | errors present? | handle_error or draft_email_reply |
| `after_hold_validation` | validate_hold_request | errors present? | handle_error or create_calendar_hold |
| `after_pet_read` | read_pet_tracker | errors / operation type | handle_error, prepare_pet_update, or END |
| `after_lead_assignment` | assign_event_lead | errors present? | handle_error or schedule_reminders |

### 6.4 Shared Utilities

**File:** `langgraph-agent/app/graph/nodes/shared.py`

| Utility | Signature | Description |
|---------|-----------|-------------|
| `llm` | `ChatAnthropic` instance | Claude Sonnet 4 client, 1024 max tokens, configurable timeout |
| `_invoke_with_retry(messages)` | `list[dict] -> str` | Exponential backoff retry (1s, 2s, 4s) for up to 3 attempts |
| `_parse_json_response(text)` | `str -> dict` | Extracts JSON from markdown code blocks or raw text |
| `_sanitize_string(value)` | `str -> str` | Strips control chars, collapses whitespace, truncates to 5000 chars |

---

## 7. Capability Specifications

### 7.1 Event Intake

**Task type:** `event_intake`
**Trigger:** POST `/api/v1/evaluate`
**Auth:** Webhook secret
**LLM calls:** 4-5 (eligibility, pricing, room setup, draft response)

**Pipeline:**

```
validate_input -> evaluate_eligibility -> [eligible?]
    |                                         |
    | (errors)                    Yes          |  No
    v                              |           v
handle_error              determine_pricing   draft_rejection -> END
                               |
                        evaluate_room_setup
                               |
                       draft_approval_response -> END
                               |
                     (on approval: auto-generate quote v1)
```

**Validation Rules (validate_input):**
- Required fields: request_id, requester_name, requester_email, event_name, requested_date, requested_start_time, requested_end_time
- Date format: YYYY-MM-DD
- Time format: HH:MM
- Start time must be before end time
- Email must contain `@`
- Estimated attendees: 1-500
- Room must be a valid room_type enum value
- Request ID: alphanumeric with hyphens/underscores, max 64 chars

**Eligibility Evaluation (evaluate_eligibility):**
- LLM evaluates against 5-tier priority system (ACC internal > government > nonprofit > community partner > external)
- Automatic exclusions: purely commercial events, political campaigns, religious worship, discriminatory events
- Returns: `is_eligible` (bool), `eligibility_reason` (str), `tier_suggestion` (str)

**Pricing Determination (determine_pricing):**
- LLM classifies into pricing tier based on organization/event
- Cost computed from: `billable_hours * hourly_rate` where `billable_hours = max(duration, minimum_hours)`
- A-EVENT deposits: 5% of cost, cost center CC05070

**Room Setup (evaluate_room_setup):**
- Auto-assigns smallest suitable room if requested room cannot accommodate attendees
- LLM parses free-text setup requirements into structured config
- Validates equipment availability against room config
- Returns: arrangement type, furniture count, AV requirements

**Database Persistence:**
- Reservation saved as `pending_review` status
- Audit trail entry: `agent_evaluated` with decision, pricing, cost, errors

**Post-Approval Side Effects:**
- Auto-generates quote v1 via `build_initial_quote()` (continueOnFail)
- Auto-generates compliance checklist via `generate_checklist()` (continueOnFail)
- Quote amount embedded in approval email draft

### 7.2 Automatic Acknowledgment Emails

**Trigger:** POST `/api/v1/acknowledge`
**Auth:** Webhook secret
**LLM calls:** 0

Sends an immediate "Thank you — request received" email when a new event request arrives. Uses the `ACKNOWLEDGMENT_EMAIL_TEMPLATE` from `cgcs_constants.py`. Personalized with the requester's first name and references the 3 business day response commitment.

### 7.3 Email Triage

**Task type:** `email_triage`
**Trigger:** POST `/api/v1/email/triage`
**Auth:** Webhook secret
**LLM calls:** 1-2 (classify + draft reply)

**Pipeline:**

```
classify_email -> [errors?]
                      |
           No errors  |  Errors
              |       v
    draft_email_reply  handle_error
              |
       check_auto_send -> END
```

**Pre-LLM Classification Rules:**

| Sender Pattern | Action | Category |
|---------------|--------|----------|
| `notifications@aais.com` or `noreply@aais.com` | Auto-classify | `aais_receipt` |
| Subject contains "has been approved" (AAIS) | Surface at medium priority | `aais_receipt` |
| Other AAIS emails | Mark read, skip processing | `aais_receipt` |
| `.ics`, `text/calendar`, `BEGIN:VCALENDAR` in body | Leave for manual handling | `calendar_invite` |

**LLM Classification:**
- 11 categories: event_request, intake_followup, aais_receipt, smartsheet_notification, calendar_invite, question, follow_up, complaint, vendor, spam, other
- 3 priority levels: high, medium, low
- VIP sender boost: `michelle.raymond@austincc.edu` or "Office of the Chancellor" in subject -> automatic `high` priority

**Self-Improving Draft System:**
- When drafting replies, the system injects up to 5 recent rejection lessons into the prompt via `get_rejection_lessons()`
- Lessons come from the `email_rejection_patterns` table, formatted as "AVOID: {what_went_wrong}" directives
- This causes the system to learn from admin corrections over time

**Auto-Send Logic:**
- Only 2 emails in allowlist: `stefano.casafrancalaos@austincc.edu`, `marisela.perez@austincc.edu`
- Calendar invites and AAIS receipts: never auto-send
- All other emails: require admin approval (`decision: "needs_review"`)

### 7.4 Self-Improving Email Rejection & Rework

**Trigger:** POST `/api/v1/email/reject-and-rework/{email_id}`
**Auth:** API key
**LLM calls:** 1 (generates 3 improved versions)

When the admin rejects an AI-drafted email:
1. Admin provides rejection reason and category (tone, content, accuracy, formatting, other)
2. System stores rejection pattern in `email_rejection_patterns` table
3. System generates 3 improved versions: Conservative, Moderate, Bold
4. Admin selects one or provides custom text via `POST /api/v1/email/select-revision/{pattern_id}`
5. Lessons from rejections are fed back into future email drafting prompts

**Rejection Insights:** `GET /api/v1/email/rejection-insights` returns:
- Total rejections, improvement rate, top categories, recent patterns
- Optionally filtered by category

### 7.5 Calendar Operations

**Task type:** `calendar_check`
**Trigger:** POST `/api/v1/calendar/check`
**Auth:** Webhook secret
**LLM calls:** 0

Queries the CGCS Events Google Calendar via REST API using service account authentication. Returns availability status and list of conflicting events. Timezone: America/Chicago (CT).

### 7.6 Calendar Hold

**Task type:** `calendar_hold`
**Trigger:** POST `/api/v1/calendar/hold`
**Auth:** API key
**LLM calls:** 0

**Calendar Entry Template Fields (30):**
Event Name, Status, Department, Date/Time, CGCS Lead, Contact Name/Event Lead, Organization/Department, Email, Phone, Attendance Estimate, Restricted, Ad Astra #, TDX #, Room(s) Reserved, Floor Layout, Stage Needed, Breakdown Time, Additional Needs, Walkthrough Date, Money Expected, Invoice Generated, Deposit Paid, Payment Method, Cost Center, Spend Category, Tax-Exempt Status, Quote Amount, Final Invoice Amount, Billing Notes, Setup Details, AV Details, Catering Details, Police Coverage, Marketing Needs, CGCS Labor Notes, Post-Event Notes

**Calendar Title Convention:**
- `HOLD` -> `"HOLD - {org_name}"`
- `S-EVENT` -> `"S-EVENT-{event_name}"`
- `C-EVENT` -> `"C-EVENT-{event_name}"`
- `A-EVENT` -> `"A-EVENT-{event_name}"`

Color: Banana yellow (colorId: 5) for holds.

### 7.7 P.E.T. Tracker

**Task type:** `pet_tracker`
**Trigger:** POST `/api/v1/pet/query` (read), POST `/api/v1/pet/update` (update)
**Auth:** API key
**LLM calls:** 0

**Operations:**
- **Read**: Fetches all data from the P.E.T. tracker Google Sheet. Supports simple text filter via `query` parameter (case-insensitive substring match across all cells).
- **Update**: Stages row data changes. Returns a `staged_id`. Requires separate admin approval via `POST /api/v1/pet/update/{staged_id}/approve` before applying to the spreadsheet.

**P.E.T. Tracker Columns (20):**
Event Name, Status, Entered into Calendar, CGCS/AMI/STEWARDSHIP, Date of event, Time of event, CGCS Lead, Contact Information/Event Lead, Attendance, Money Expected, Ad Astra Number #, TDX Request #, Floor Layout, Stage?, Breakdown Time Needed, Additional Needs, Walkthrough Date, Invoice Generated, Rooms, CGCS Labor

### 7.8 Event Lead Assignment

**Task type:** `event_lead`
**Trigger:** POST `/api/v1/leads/assign`
**Auth:** API key
**LLM calls:** 0

**Staff Roster (8 members):**

| Name | Email |
|------|-------|
| Brenden Fogg | brenden.fogg@g.austincc.edu |
| Bryan Port | bryan.port@austincc.edu |
| Catherine Thomason | catherine.thomason@austincc.edu |
| Eimanie Thomas | eimanie.thomas@g.austincc.edu |
| Marisela Perez Maita | marisela.perezmaita@austincc.edu |
| Stefano Casafranca Laos | stefano.casafrancalaos@austincc.edu |
| Tzur Shalit | tzur.shalit@g.austincc.edu |
| Vanessa Trujano | vanessa.trujano@g.austincc.edu |

**Business Rules:**
- Staff email must be in the roster (validated at assignment time)
- Monthly lead cap: 3 leads per staff member per calendar month
- Reminder auto-scheduling: 30d, 14d, 7d, 48h before event date
- Only future reminders are scheduled (dates >= today)

### 7.9 Reminders

**Task type:** `reminder_check`
**Trigger:** POST `/api/v1/reminders/check`
**Auth:** Webhook secret
**LLM calls:** 0

Processes reminders in two phases:
1. **find_due_reminders**: Filters reminders_due list for items where `remind_date <= today` and `status == "pending"`
2. **send_reminders**: Marks each due reminder as `sent` with timestamp (in production, sends via Zoho Mail API)

**Reminder Intervals:**

| Label | Days Before Event |
|-------|------------------|
| `30_day` | 30 |
| `14_day` | 14 |
| `7_day` | 7 |
| `48_hour` | 2 |

### 7.10 Revenue Tracking

**Trigger:** POST `/api/v1/reservation/{request_id}/complete`
**Auth:** API key
**LLM calls:** 0

Records actual revenue and attendance when events complete:
- `actual_revenue`, `actual_attendees`, `event_type`
- Revenue reports by period (week/month/quarter/year) with breakdowns by event type
- CSV export via `GET /api/v1/reports/export`
- Top organizations ranking via `GET /api/v1/reports/top-organizations`
- Conversion funnel via `GET /api/v1/reports/conversion-funnel`

### 7.11 Compliance Checklist

**Trigger:** Auto-generated on intake approval + manual endpoints
**Auth:** API key
**LLM calls:** 0

**10-Item Event Checklist (EVENT_CHECKLIST_TEMPLATE):**

| Item Key | Label | Default Days Before | Conditional |
|----------|-------|--------------------:|-------------|
| `user_agreement` | User Agreement Signed | 20 | Always |
| `furniture_layout` | Furniture Layout Confirmed | 20 | Always |
| `catering_plan` | Catering Plan Confirmed | 25 | Always |
| `run_of_show` | Run of Show Submitted | 20 | Always |
| `walkthrough` | Walkthrough Scheduled | 12 | Always |
| `tdx_av_request` | TDX AV Request Submitted | 15 | Always |
| `payment_received` | Payment Received | 10 | A-EVENT only |
| `police_security` | Police/Security Arranged | 10 | Weekend/evening events |
| `insurance_docs` | Insurance Documents Received | 14 | External tier only |
| `parking_confirmed` | Parking Arrangements Confirmed | 5 | Attendance > 50 |

**Business-day deadline calculation** using Python's `weekday()` to skip weekends.

**Endpoints:**
- `GET /api/v1/checklist/{request_id}` — Get checklist for reservation
- `POST /api/v1/checklist/{request_id}/bulk-update` — Bulk update items
- `POST /api/v1/checklist/{request_id}/{item_key}` — Update single item
- `GET /api/v1/reports/compliance` — Compliance report with on-time rates

### 7.12 Dynamic Quote Versioning

**Trigger:** Auto-generated on intake approval + manual endpoints
**Auth:** API key
**LLM calls:** 0

**Quote Builder (services/quote_builder.py):**
- Pure functions with zero DB/async dependencies for easy testing
- `build_initial_quote(reservation)` → generates v1 with line items from pricing tier + add-ons
- `update_quote(current_quote, changes)` → creates new version with diff tracking
- `format_quote_for_email(quote)` → formatted text for inclusion in approval emails

**11 Service Types:**
room_rental, av_equipment, acc_technician, furniture_rental, round_tables, stage_setup, stage_teardown, admin_support, signage, catering_coordination, police_security

**Endpoints:**
- `POST /api/v1/quote/generate/{request_id}` — Generate initial quote (v1)
- `POST /api/v1/quote/update/{request_id}` — Add/remove services, create new version
- `GET /api/v1/quote/history/{request_id}` — All quote versions
- `GET /api/v1/quote/latest/{request_id}` — Latest version

### 7.13 Process Insights & Quarterly Reports

**File:** `langgraph-agent/app/services/process_insights.py`
**Auth:** API key
**LLM calls:** 1 (recommendations generation)

Analytics layer that queries across all operational data:

| Function | Data Source | Metrics |
|----------|------------|---------|
| `get_email_metrics()` | email_tasks, email_rejection_patterns | total_drafts, rejection_rate, avg_revisions, top_rejection_reasons, improvement_trend |
| `get_quote_metrics()` | quote_versions | total_quotes, avg_revisions, most_added_service, avg_quote_increase_pct |
| `get_turnaround_metrics()` | reservations, audit_trail | avg_intake_to_response_hours, avg_intake_to_approval_days, avg_intake_to_event_days |
| `get_compliance_metrics()` | event_checklist, reservations | on_time_rate, most_overdue_items, avg_overdue_days, items_never_completed |
| `get_conversion_funnel_metrics()` | reservations | submitted/approved/completed/cancelled/rejected counts, conversion_rate |
| `generate_recommendations()` | all metrics combined | 3-5 Claude-powered actionable recommendations |
| `build_quarterly_report()` | all of the above + revenue + top orgs | Combined report with continueOnFail per section |
| `get_monthly_quick_stats()` | reservations, event_checklist | Lightweight monthly stats for daily digest |

**Endpoints:**
- `GET /api/v1/reports/process-insights?period=quarter&start=2026-01-01` — Full combined report
- `POST /api/v1/reports/generate-quarterly` — Generate quarterly report, optionally email

### 7.14 Daily Digest

**Task type:** `daily_digest`
**Trigger:** POST `/api/v1/daily-digest`
**Auth:** Webhook secret
**LLM calls:** 0

Generates a **9-section** daily summary email for the admin:

1. **Pending Approvals** — Items awaiting admin decision
2. **New Intakes** — Recent reservation requests with up to 3 suggested reply options
3. **Upcoming Events (Next 30 Days)** — With status, lead, and overdue action flags
4. **Due Reminders Today** — Reminders scheduled for the current date
5. **Pending User Agreements** — Sent but not returned agreements
6. **Overdue Deadline Warnings** — Events past critical deadlines
7. **Checklist Items Due This Week** — Compliance items approaching deadline
8. **Deadline Reference** — CGCS response (3 bd), TDX AV (15 bd), walkthrough (12 bd), ACC catering (25 bd), run of show/furniture (20 bd)
9. **Quick Stats — This Month** — Events, revenue, pending approvals, on-time checklist rate

---

## 8. API Specification

### 8.1 Base URL

- Local: `http://localhost:8000`
- Production: `https://agent.{DOMAIN}` (Caddy reverse proxy, restricted to internal IPs)

### 8.2 API Version

All endpoints are under `/api/v1/`.

### 8.3 Endpoint Reference (38 total)

#### Health

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/api/v1/health` | None | - | `HealthResponse` |

#### Core Intake & Admin

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/acknowledge` | Webhook | Send auto-acknowledgment email |
| POST | `/api/v1/evaluate` | Webhook | Process event intake through full pipeline |
| POST | `/api/v1/approve/{request_id}` | API Key | Admin approve/reject reservation |
| GET | `/api/v1/reservation/{request_id}` | API Key | Lookup reservation details |
| POST | `/api/v1/reservation/{request_id}/complete` | API Key | Mark reservation completed with actuals |
| GET | `/api/v1/staff-roster` | API Key | Current staff roster |
| GET | `/api/v1/dead-letter` | API Key | List failed requests |
| POST | `/api/v1/dead-letter/{id}/resolve` | API Key | Resolve DLQ entry |

#### Email Triage & Self-Improving Drafts

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/email/triage` | Webhook | Classify email, draft reply, check auto-send |
| POST | `/api/v1/email/approve/{email_id}` | API Key | Approve/reject email draft |
| GET | `/api/v1/email/pending` | API Key | List pending email drafts |
| POST | `/api/v1/email/reject-and-rework/{email_id}` | API Key | Reject draft, generate 3 improved versions |
| POST | `/api/v1/email/select-revision/{pattern_id}` | API Key | Select revision or provide custom draft |
| GET | `/api/v1/email/rejection-insights` | API Key | Rejection analytics and improvement rate |

#### Calendar Operations

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/calendar/check` | Webhook | Check Google Calendar availability |
| POST | `/api/v1/calendar/hold` | API Key | Create calendar hold |

#### P.E.T. Tracker

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/pet/query` | API Key | Query P.E.T. tracker spreadsheet |
| POST | `/api/v1/pet/update` | API Key | Stage P.E.T. update for approval |
| POST | `/api/v1/pet/update/{id}/approve` | API Key | Apply staged P.E.T. update |

#### Event Leads & Reminders

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/leads/assign` | API Key | Assign event lead + schedule reminders |
| GET | `/api/v1/leads/{reservation_id}` | API Key | Get lead for event |
| POST | `/api/v1/reminders/check` | Webhook | Find and process due reminders |
| POST | `/api/v1/daily-digest` | Webhook | Generate admin daily digest (9 sections) |

#### Compliance Checklist

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/v1/checklist/{request_id}` | API Key | Get checklist for reservation |
| POST | `/api/v1/checklist/{request_id}/bulk-update` | API Key | Bulk update checklist items |
| POST | `/api/v1/checklist/{request_id}/{item_key}` | API Key | Update single checklist item |

#### Dynamic Quote Versioning

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/quote/generate/{request_id}` | API Key | Generate initial quote (v1) |
| POST | `/api/v1/quote/update/{request_id}` | API Key | Add/remove services, create new version |
| GET | `/api/v1/quote/history/{request_id}` | API Key | All quote versions for a reservation |
| GET | `/api/v1/quote/latest/{request_id}` | API Key | Latest quote version |

#### Reports & Analytics

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/v1/reports/revenue` | API Key | Revenue aggregation report |
| GET | `/api/v1/reports/conversion-funnel` | API Key | Reservation conversion funnel |
| GET | `/api/v1/reports/export` | API Key | CSV export of reservations |
| GET | `/api/v1/reports/top-organizations` | API Key | Top organizations by booking count |
| GET | `/api/v1/reports/compliance` | API Key | Compliance on-time rates and overdue items |
| GET | `/api/v1/reports/process-insights` | API Key | Full process insights with AI recommendations |
| POST | `/api/v1/reports/generate-quarterly` | API Key | Generate quarterly report, optionally email |

### 8.4 Error Responses

| Status Code | Meaning | Example |
|-------------|---------|---------|
| 400 | Bad request / invalid state transition | `"Reservation is already approved, cannot modify"` |
| 401 | Authentication failed | `"Invalid API key"` or `"Invalid webhook secret"` |
| 404 | Resource not found | `"Reservation not found"` |
| 409 | Conflict / concurrent update | `"Failed to update reservation"` |
| 422 | Validation error (Pydantic) | Automatic from request model validation |

---

## 9. Database Schema

### 9.1 Overview

- **Engine:** PostgreSQL 16
- **Schema:** `cgcs` (separate from N8N's tables in public schema)
- **Driver:** asyncpg with connection pool (min 2, max 10)
- **Tables:** 11
- **Migrations:** 9 files (001–009), applied automatically on container startup

### 9.2 Table Inventory

| Table | Migration | Purpose |
|-------|-----------|---------|
| `reservations` | 001, 005 | Event space reservations with full lifecycle + revenue actuals |
| `audit_trail` | 001 | Activity log for all task types |
| `dead_letter_queue` | 001 | Failed request recovery |
| `pricing_rules` | 001, 002 | Reference: 5 pricing tiers |
| `room_configurations` | 001, 002 | Reference: 5 room configs |
| `email_tasks` | 003 | Email triage records |
| `event_leads` | 003 | Staff lead assignments (one per event) |
| `event_reminders` | 003 | Scheduled reminders at 30d/14d/7d/48h |
| `calendar_holds` | 003 | Tentative calendar reservations |
| `pet_staged_updates` | 003 | Staged P.E.T. updates awaiting approval |
| `event_checklist` | 007 | Compliance checklist items with deadlines |
| `email_rejection_patterns` | 008 | Email draft rejection history and revisions |
| `quote_versions` | 009 | Versioned line-item quotes per reservation |

### 9.3 New Tables (v2.0)

#### cgcs.event_checklist (Migration 007)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| reservation_id | UUID | FK -> reservations(id) | Related reservation |
| item_key | VARCHAR(50) | NOT NULL | Checklist item identifier |
| item_label | VARCHAR(255) | NOT NULL | Human-readable label |
| deadline_date | DATE | | Business-day-calculated deadline |
| completed | BOOLEAN | DEFAULT FALSE | Completion status |
| completed_at | TIMESTAMPTZ | | When completed |
| completed_by | VARCHAR(100) | | Who completed it |
| notes | TEXT | | Admin notes |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | Last modification |

**Indexes:** reservation_id, (reservation_id, item_key) UNIQUE
**Constraint:** One row per (reservation_id, item_key)

#### cgcs.email_rejection_patterns (Migration 008)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| email_task_id | UUID | FK -> email_tasks(id) | Related email task |
| rejection_reason | TEXT | NOT NULL | Admin's rejection explanation |
| rejection_category | VARCHAR(50) | DEFAULT 'other' | tone/content/accuracy/formatting/other |
| original_draft | TEXT | | The draft that was rejected |
| improved_versions | JSONB | | 3 improved versions (Conservative/Moderate/Bold) |
| selected_version | INTEGER | | Which version admin chose (1-3) or null for custom |
| custom_draft | TEXT | | Custom draft if admin wrote their own |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |

**Indexes:** email_task_id, rejection_category, created_at

#### cgcs.quote_versions (Migration 009)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| reservation_id | UUID | FK -> reservations(id) | Related reservation |
| version_number | INTEGER | NOT NULL | Sequential version (1, 2, 3...) |
| line_items | JSONB | NOT NULL | Array of {service, description, quantity, unit_price, total} |
| subtotal | DECIMAL(10,2) | | Sum of line items |
| tax_amount | DECIMAL(10,2) | DEFAULT 0 | Tax (if applicable) |
| total_amount | DECIMAL(10,2) | | Subtotal + tax |
| changes_from_previous | JSONB | | Diff from prior version: {added: [], removed: [], modified: []} |
| notes | TEXT | | Version notes |
| created_by | VARCHAR(100) | DEFAULT 'system' | Creator |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |

**Indexes:** reservation_id, (reservation_id, version_number) UNIQUE

#### Revenue Columns on Reservations (Migration 005)

| Column | Type | Description |
|--------|------|-------------|
| actual_revenue | DECIMAL(10,2) | Actual revenue collected |
| actual_attendees | INTEGER | Actual attendance |
| event_type | VARCHAR(20) | S-EVENT, C-EVENT, A-EVENT |
| completed_at | TIMESTAMPTZ | When event was completed |

### 9.4 Existing Tables (Unchanged from v1.0)

Tables from v1.0 (reservations, audit_trail, email_tasks, event_leads, event_reminders, calendar_holds, pet_staged_updates, dead_letter_queue, pricing_rules, room_configurations) retain their original schemas. See v1.0 specification for full column details.

### 9.5 Automatic Triggers

All tables with `updated_at` columns use the shared trigger function:

```sql
CREATE OR REPLACE FUNCTION cgcs.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## 10. External Service Integrations

### 10.1 Google Calendar API

**File:** `langgraph-agent/app/services/google_calendar.py`
**Authentication:** Service account (GOOGLE_SERVICE_ACCOUNT_FILE)
**Scope:** `https://www.googleapis.com/auth/calendar`
**Timezone:** America/Chicago (CT, UTC-6)

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Check availability | GET | `/calendar/v3/calendars/{calendarId}/events` |
| Create hold | POST | `/calendar/v3/calendars/{calendarId}/events` |

**Retry:** 3 attempts with exponential backoff (1s, 2s, 4s). HTTP client timeout: 30s.

### 10.2 Google Sheets API

**File:** `langgraph-agent/app/services/google_sheets.py`
**Authentication:** Service account (GOOGLE_SERVICE_ACCOUNT_FILE)
**Scope:** `https://www.googleapis.com/auth/spreadsheets`

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Read sheet | GET | `/v4/spreadsheets/{spreadsheetId}/values/{range}` |
| Apply update | PUT | `/v4/spreadsheets/{spreadsheetId}/values/{range}?valueInputOption=USER_ENTERED` |

### 10.3 Zoho Mail API (LEGACY — being migrated to Gmail API)

**File:** `langgraph-agent/app/services/zoho_mail.py`
**Authentication:** OAuth token (ZOHO_MAIL_TOKEN)
**Base URL:** `https://mail.zoho.com/api`
**System email:** `admin@cgcsacc.org` (current)

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Fetch unread | GET | `/accounts/{accountId}/messages/view` |
| Send email | POST | `/accounts/{accountId}/messages` |

**Retry:** 3 attempts with exponential backoff. HTTP client timeout: 30s.

**Migration note:** This service will be replaced with Gmail API once the Google Workspace account (`admin@cgcs-acc.org`) is fully configured. The service interface (`fetch_unread`, `send_email`) will remain the same — only the underlying provider changes.

### 10.4 Anthropic Claude API

**Integration:** Via `langchain-anthropic` (`ChatAnthropic`)
**Model:** `claude-sonnet-4-20250514` (configurable via `CLAUDE_MODEL` env var)
**Max tokens:** 1024
**Timeout:** 60s (configurable via `LLM_TIMEOUT`)
**Retry:** 3 attempts (configurable via `LLM_MAX_RETRIES`) with exponential backoff starting at 1.0s (configurable via `LLM_RETRY_BASE_DELAY`)

**LLM Usage by Feature:**

| Feature | LLM Calls | Purpose |
|---------|-----------|---------|
| Event Intake | 4-5 | Eligibility, pricing, room setup, draft response |
| Email Triage | 1-2 | Classification + draft reply |
| Email Rework | 1 | Generate 3 improved versions |
| Process Insights | 1 | Generate recommendations |
| Other capabilities | 0 | Pure logic / API calls only |

---

## 11. Authentication & Authorization

### 11.1 Authentication Schemes

The system uses two authentication mechanisms, neither of which involves user session management:

#### Webhook Secret Authentication

- **Header:** `X-Webhook-Secret`
- **Mechanism:** Shared secret comparison
- **Used by:** N8N workflows and cron-triggered endpoints
- **Endpoints:** `/api/v1/evaluate`, `/api/v1/acknowledge`, `/api/v1/email/triage`, `/api/v1/calendar/check`, `/api/v1/reminders/check`, `/api/v1/daily-digest`
- **Graceful degradation:** If `WEBHOOK_SECRET` is not configured, all requests pass (returns "no-secret-configured")

#### API Key Authentication

- **Header:** `Authorization: Bearer {LANGGRAPH_API_KEY}`
- **Mechanism:** Bearer token comparison
- **Used by:** CGCS Command dashboard, internal API consumers
- **Endpoints:** All admin, checklist, quote, report, email rejection, and DLQ endpoints
- **Graceful degradation:** If `LANGGRAPH_API_KEY` is not configured, all requests pass (returns "anonymous")

### 11.2 Network-Level Access Control

The Caddy reverse proxy restricts agent API access to internal networks:

```
@blocked not remote_ip 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.1/8
respond @blocked 403
```

Only RFC 1918 private addresses and localhost can reach the agent API.

### 11.3 OpenAPI Documentation

Swagger UI (`/docs`) is disabled in production:

```python
docs_url=None if settings.environment == "production" else "/docs"
redoc_url=None  # Always disabled
```

---

## 12. Human-in-the-Loop Architecture

### 12.1 Current State (v2.0)

N8N serves as the **trigger/orchestration layer** — it receives webhooks, runs cron jobs, and calls the agent API. However, N8N is **not the primary admin interface**. It was never designed to be an approval dashboard.

The human-in-the-loop interface is split:

| Interface | Role | What It Does |
|-----------|------|-------------|
| **N8N** | Trigger orchestration | Receives form webhooks, polls Zoho email (cron), triggers daily digest (cron), calls agent API |
| **LangSmith** | LLM observability + review | Traces every LLM call, shows full prompt/response, allows run comparison, flags anomalies |
| **Agent API (direct)** | Admin actions | Approve/reject reservations, approve emails, reject-and-rework, checklist updates, quote generation |

### 12.2 Why Not Just N8N?

N8N is a workflow automation tool, not an admin dashboard. Using N8N as the approval UI means:
- Austin clicks through workflow nodes to see pending items (poor UX)
- No aggregated view of all pending work
- No analytics or trends
- No mobile-friendly interface

### 12.3 Why LangSmith for HITL?

LangSmith provides:
- **Run tracing**: See exactly what Claude was asked and what it responded
- **Annotation queues**: Mark runs as correct/incorrect for evaluation
- **Comparison**: Side-by-side view of different runs
- **Feedback collection**: Thumbs up/down on LLM outputs
- **Alerting**: Get notified when runs fail or produce unexpected results

This makes LangSmith the best current option for monitoring and evaluating AI decisions, while a purpose-built dashboard (CGCS Command) handles operational approvals.

### 12.4 CGCS Command Dashboard (Planned)

A purpose-built admin dashboard for operational use:

**Core Screens:**
- **Inbox**: Pending approvals (reservations + emails) in one view
- **Events**: Calendar with upcoming events, leads, checklist status
- **Analytics**: Revenue trends, conversion funnel, compliance heatmap, top orgs
- **Settings**: Staff roster, labor rates, deadline configuration

**Tech Stack (planned):**
- Next.js + React
- Recharts for data visualization
- API key auth against the existing FastAPI backend
- Real-time updates via polling or WebSockets

### 12.5 N8N Workflow Inventory

N8N is retained for **trigger orchestration only**:

| Workflow | Trigger | Flow |
|----------|---------|------|
| **Event Space Intake** | Webhook (form submission) | Receive form data -> check Google Calendar availability -> POST `/api/v1/evaluate` -> POST `/api/v1/acknowledge` |
| **Admin Approval** | Webhook (admin action) | Receive approve/reject -> POST `/api/v1/approve/{request_id}` -> send email to requester via Zoho |
| **Email Monitoring** | Cron (every 5 minutes) | Poll Zoho Mail inbox -> for each unread email -> POST `/api/v1/email/triage` -> route to admin if not auto-send |
| **Calendar Hold** | Manual trigger | Admin inputs org/date/time -> POST `/api/v1/calendar/hold` -> confirm creation |
| **Reminder Cron** | Cron (8:00 AM CT daily) | POST `/api/v1/reminders/check` -> POST `/api/v1/daily-digest` -> send digest to admin |

---

## 13. Business Rules & Constants

**File:** `langgraph-agent/app/cgcs_constants.py`

### 13.1 Hours of Operation

| Day | Building Hours | Event Hours |
|-----|---------------|-------------|
| Monday-Thursday | 7:00 AM - 10:00 PM | 8:00 AM - 9:00 PM |
| Friday | 7:00 AM - 5:00 PM | 8:00 AM - 4:30 PM |
| Weekend | Conditional | Requires police ($65/hr) + police agreement + CGCS support staff |

### 13.2 Pricing Tiers

| Tier | Hourly Rate | Minimum Hours | Description |
|------|-------------|---------------|-------------|
| acc_internal | $0.00 | 1 | ACC departments, programs, faculty, staff |
| government_agency | $0.00 | 1 | Federal, state, local government agencies |
| nonprofit | $25.00 | 2 | Nonprofit organizations with civic/government missions |
| community_partner | $50.00 | 2 | Community partners with educational missions |
| external | $100.00 | 3 | External organizations |

### 13.3 AMI Facility Pricing (A-EVENT)

| Block | Price |
|-------|-------|
| Morning | $500 |
| Afternoon | $500 |
| Evening | $500 |
| Full Day | $1,000 |
| Extended | $1,250 |
| Friday Evening/Weekend | $750 |
| Weekend Hourly | $200/hr |

### 13.4 Add-On Services (11 types)

| Service | Rate | Unit |
|---------|------|------|
| AV Equipment | $60 | per hour (+$100 webcast surcharge) |
| ACC Technician | $160 | flat |
| Furniture Rental | $250 | flat |
| Round Tables | $15 | each (includes linens + ACC moving team) |
| Stage Setup | $150 | flat |
| Stage Teardown | $100 | flat |
| Admin Support | Up to $250 | flat |
| Signage | $100 | flat |
| Catering Coordination | $100 | surcharge |
| Police | $65 | per hour (4-hour minimum) |

### 13.5 Labor Rates (NEW in v2.0)

| Role | Staff | Hourly Rate |
|------|-------|-------------|
| Director / Event Lead | Bryan Port | $66.00 |
| Intern Event Lead | Brenden Fogg, Catherine Thomason, Eimanie Thomas, Marisela Perez Maita, Stefano Casafranca Laos, Tzur Shalit, Vanessa Trujano | $25.00 |
| Intake Processing | Austin Wells | $25.00 |

**Helper:** `get_labor_rate(staff_name) -> float` returns the hourly rate for any staff member (0.0 for unknown).

**Time Constants:**
- `DEFAULT_PREP_TIME_HOURS = 1.0`
- `DEFAULT_BREAKDOWN_HOURS = 0.5`

### 13.6 Deadlines (Business Days Before Event)

| Deadline | Business Days |
|----------|--------------|
| CGCS Response | 3 |
| TDX AV Request | 15 |
| Walkthrough | 12 |
| ACC Catering | 25 |
| Run of Show / Furniture | 20 |

### 13.7 Financial

- **A-EVENT Deposit Rate:** 5%
- **Cost Center:** CC05070

### 13.8 Room Configurations

| Room | Display Name | Max Capacity | Equipment | Setup Options |
|------|-------------|-------------|-----------|---------------|
| large_conference | Large Conference Room | 60 | Projector, screen, whiteboard, mic, speakers, video conferencing, WiFi | Theater(60), Classroom(30), Boardroom(24), U-Shape(20), Banquet(40) |
| small_conference | Small Conference Room | 15 | Projector, screen, whiteboard, video conferencing, WiFi | Boardroom(15), U-Shape(10) |
| event_hall | Event Hall | 200 | Projector, screen, mic, speakers, stage, WiFi, catering kitchen | Theater(200), Banquet(120), Reception(150), Classroom(80) |
| classroom | Classroom | 40 | Projector, screen, whiteboard, WiFi | Classroom(40), Theater(40), U-Shape(20) |
| multipurpose | Multipurpose Room | 80 | Projector, screen, whiteboard, mic, speakers, WiFi | Theater(80), Classroom(40), Banquet(50), Reception(70) |

### 13.9 Room Auto-Assignment Algorithm

When the requested room cannot accommodate the attendee count:

```python
# Sort rooms by max_capacity ascending, select smallest that fits
for room_key, config in sorted(ROOM_CONFIGS.items(), key=lambda x: x[1]["max_capacity"]):
    if config["max_capacity"] >= attendees:
        return room_key
```

### 13.10 Eligibility Rules

**Priority order:** acc_internal > government_agency > nonprofit > community_partner > external

**Always eligible:** acc_internal, government_agency

**Exclusions (never eligible):**
1. Purely commercial events (product launches, sales events, trade shows)
2. Political campaign events or fundraisers for candidates
3. Religious worship services (educational events about religion are OK)
4. Events that promote discrimination or violate ACC policies

### 13.11 Event Type Classification

| Prefix | Description |
|--------|-------------|
| S-EVENT | Service/partner/internal (no revenue) |
| C-EVENT | CGCS programs |
| A-EVENT | Paid/AMI (revenue-generating) |

### 13.12 VIP & Auto-Send Rules

**VIP Senders (auto-boost to high priority):**
- `michelle.raymond@austincc.edu` (ACC Strategic Planning)
- Any email mentioning "Office of the Chancellor" in subject

**Auto-Send Allowlist:**
- `stefano.casafrancalaos@austincc.edu`
- `marisela.perez@austincc.edu`

**Ad Astra (AAIS) Email Handling:**
- Sender emails: `notifications@aais.com`, `noreply@aais.com`
- Subject pattern: `Event Reservation #\d{8}-\d{5}`
- Only surface if "has been approved" in subject; otherwise mark read

### 13.13 Acknowledgment Email Template

```
Dear {first_name},

Thank you for submitting your event space reservation request to the Center for Government & Civic Service at Austin Community College.

We have received your request and it is now being reviewed. You can expect a response within 3 business days.

If you have any questions in the meantime, please don't hesitate to reach out.

Best regards,
Austin Wells
Strategic Planner for Community Relations & Environmental Affairs
Center for Government & Civic Service
Austin Community College
```

### 13.14 Event Checklist Template

See Section 7.11 for the full 10-item checklist with conditional logic.

---

## 14. Prompt Engineering

**File:** `langgraph-agent/app/prompts/templates.py`

### 14.1 Prompt Inventory

| Prompt | Variable | Used In | Purpose |
|--------|----------|---------|---------|
| `ELIGIBILITY_SYSTEM_PROMPT` | Static | `evaluate_eligibility` | Determine if event meets CGCS criteria |
| `PRICING_SYSTEM_PROMPT` | Static | `determine_pricing` | Classify organization into pricing tier |
| `SETUP_SYSTEM_PROMPT` | Parameterized | `evaluate_room_setup` | Parse setup requirements into structured config |
| `APPROVAL_RESPONSE_SYSTEM_PROMPT` | Parameterized | `draft_approval_response` | Draft professional approval email (with quote) |
| `REJECTION_RESPONSE_SYSTEM_PROMPT` | Parameterized | `draft_rejection` | Draft empathetic rejection email |
| `EMAIL_TRIAGE_SYSTEM_PROMPT` | Static | `classify_email`, `draft_email_reply` | Classify and respond to incoming emails |
| `REJECTION_REWORK_SYSTEM_PROMPT` | Parameterized | `reject_and_rework` | Generate 3 improved email versions |
| Process Recommendations | Inline | `generate_recommendations` | Generate actionable insights from metrics |

### 14.2 Self-Improving Prompts (NEW in v2.0)

**File:** `langgraph-agent/app/prompt_tuning.py`

The `get_rejection_lessons()` function queries the 5 most recent rejection patterns and formats them as directives injected into the email drafting prompt:

```
LESSONS FROM PREVIOUS CORRECTIONS:
- AVOID: Using overly formal language in responses to internal staff
- AVOID: Mentioning specific pricing before admin review
- AVOID: Promising specific dates without checking calendar
```

This creates a feedback loop where admin corrections improve future output quality.

### 14.3 Response Format

All classification prompts require **strict JSON output**:

```
Respond with ONLY valid JSON:
{
    "field": "value",
    ...
}
```

### 14.4 Email Signing Convention

All drafted emails are signed as:
> Austin Wells, Strategic Planner for Community Relations & Environmental Affairs, Center for Government & Civic Service, Austin Community College

### 14.5 Email Drafting Rules

- Never CC Bryan Port on any emails
- Include mention of user agreement PDFs for initial event responses
- Include parking map information early in the process
- Reference the 3 business day response commitment
- For spam, return empty string (no reply drafted)
- For complaints, acknowledge concerns and offer to connect with appropriate staff

---

## 15. Error Handling & Resilience

### 15.1 LLM Retry Strategy

```python
def _invoke_with_retry(messages: list[dict]) -> str:
    for attempt in range(settings.llm_max_retries):  # default: 3
        try:
            return llm.invoke(messages).content
        except Exception as e:
            if attempt < settings.llm_max_retries - 1:
                delay = settings.llm_retry_base_delay * (2 ** attempt)  # 1s, 2s, 4s
                time.sleep(delay)
    raise last_error
```

### 15.2 HTTP Retry Strategy (External APIs)

Google Calendar and Zoho Mail services use identical retry logic:
- 3 attempts
- Exponential backoff: 1s, 2s, 4s
- HTTP client timeout: 30s per request

### 15.3 Dead Letter Queue

When graph execution fails, the system **never silently drops** a request:

1. **Graph execution failure** -> Dead letter entry with `error_type: "graph_execution_failure"`
2. **Database save failure** -> Dead letter entry with `error_type: "db_save_failure"` (includes the graph result so it's not lost)
3. **DLQ write failure** -> CRITICAL log (last resort)

### 15.4 continueOnFail Pattern (NEW in v2.0)

Non-critical operations wrapped in try/except to prevent blocking the main flow:

| Operation | Failure Behavior |
|-----------|-----------------|
| Auto-quote generation on approval | Logged, approval proceeds without quote |
| Auto-checklist generation on approval | Logged, approval proceeds without checklist |
| Monthly quick stats in daily digest | Shows "Stats unavailable" in digest |
| Audit entry for quarterly report | Logged, report still returned |

### 15.5 Graceful Degradation

| Failure | Behavior |
|---------|----------|
| LLM unavailable | Request queued as "needs_review" |
| Google Calendar API down | Returns `calendar_is_available: null`, errors logged |
| Google Sheets API down | Returns `pet_result: null`, errors logged |
| Zoho Mail API down | Reminders logged but not sent, errors captured |
| Database unavailable | Request sent to DLQ (if DLQ write also fails, CRITICAL log) |
| Auth not configured | Endpoints become unauthenticated (graceful bypass) |
| Process insights query fails | Section omitted from report, other sections still included |
| Recommendations LLM fails | Returns generic fallback recommendations |

---

## 16. Security Architecture

### 16.1 Input Sanitization

All user-supplied strings pass through `_sanitize_string()`:

```python
def _sanitize_string(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)  # Strip control chars
    cleaned = re.sub(r"[ \t]+", " ", cleaned)                            # Collapse whitespace
    return cleaned[:5000].strip()                                         # Truncate
```

### 16.2 Request Validation

- **Request ID format:** `^[a-zA-Z0-9_-]{1,64}$` (prevents injection via identifiers)
- **Email validation:** Pydantic `EmailStr` type with email-validator library
- **Field length limits:** All string fields have explicit `max_length` constraints
- **Numeric bounds:** `estimated_attendees` constrained to 1-500
- **Pattern matching:** Date (`YYYY-MM-DD`), time (`HH:MM`), action (`approve|reject`)

### 16.3 SQL Injection Prevention

All database queries use parameterized queries via asyncpg:

```python
await pool.fetchrow(
    "SELECT * FROM cgcs.reservations WHERE request_id = $1",
    request_id,  # Parameterized, never interpolated
)
```

### 16.4 Container Security

- **Non-root execution:** Application runs as user `cgcs` (not root)
- **Read-only credentials:** Credentials volume mounted as `:ro`
- **Minimal base image:** `python:3.12-slim` with only required system packages
- **No shell access:** User created with `/sbin/nologin`

### 16.5 Network Security

- Agent API restricted to private IPs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.1/8)
- Auto-HTTPS via Caddy with ACME certificate management
- N8N exposed publicly only for webhook reception (with basic auth)
- Inter-service communication over private Docker bridge network (`cgcs-net`)

### 16.6 Secret Management

All secrets passed via environment variables (never committed to code):
- `ANTHROPIC_API_KEY` — Claude API access
- `LANGGRAPH_API_KEY` — Internal API authentication
- `WEBHOOK_SECRET` — N8N webhook verification
- `POSTGRES_PASSWORD` — Database access
- `N8N_ENCRYPTION_KEY` — N8N credential encryption
- `GOOGLE_SERVICE_ACCOUNT_FILE` — Google API credentials (file path)
- `ZOHO_MAIL_TOKEN` — Zoho Mail API access
- `LANGCHAIN_API_KEY` — LangSmith tracing

---

## 17. Deployment & Infrastructure

### 17.1 Docker Compose Services (4)

| Service | Image | Port | Health Check |
|---------|-------|------|-------------|
| **caddy** | `caddy:2-alpine` | 80, 443 | - |
| **n8n** | `n8nio/n8n:latest` | 5678 (internal) | - |
| **langgraph-agent** | Custom (Dockerfile) | 8000 (internal) | `curl -f http://localhost:8000/api/v1/health` every 30s |
| **postgres** | `postgres:16-alpine` | 5432 (internal) | `pg_isready` every 10s |

### 17.2 Database Initialization

Migrations are applied automatically on PostgreSQL container first start:

| File | Purpose |
|------|---------|
| `001_initial_schema.sql` | Core tables: reservations, audit, pricing, rooms, DLQ |
| `002_seed_data.sql` | Pricing tiers & room configurations |
| `003_multi_capability.sql` | Email, leads, reminders, holds, P.E.T. tables |
| `004_placeholder.sql` | Reserved |
| `005_revenue_columns.sql` | Revenue columns on reservations |
| `006_placeholder.sql` | Reserved |
| `007_event_checklist.sql` | Compliance checklist table |
| `008_rejection_patterns.sql` | Email rejection patterns table |
| `009_quote_versions.sql` | Quote versioning table |

---

## 18. Observability & Monitoring

### 18.1 LangSmith Tracing

All graph invocations are traced via LangSmith:

```python
config = {"run_name": f"{task_type}:{request_id}"}
result = compiled_graph.invoke(initial_state, config=config)
```

**Configuration:**
- Project: `cgcs-automation` (configurable via `LANGCHAIN_PROJECT`)
- Tracing enabled by default (`LANGCHAIN_TRACING_V2=true`)
- Each run is named `{task_type}:{request_id}` for easy filtering

### 18.2 LangSmith as Review Interface

Beyond tracing, LangSmith serves as the primary interface for reviewing AI decision quality:
- **Annotation queues**: Flag runs for review (e.g., all email drafts)
- **Feedback**: Thumbs up/down on individual LLM outputs
- **Run comparison**: Compare how the same prompt performs across different inputs
- **Alerting**: Notify when runs fail or produce unexpected patterns

### 18.3 Structured Logging

All modules use Python's `logging` module with configurable log level:

```python
logging.basicConfig(level=settings.log_level)  # default: INFO
```

**Key log events:**
- Task routing: `"Routing task: {task_type} (request_id={request_id})"`
- LLM failures: `"LLM call failed (attempt {n}/{max}), retrying in {delay}s: {error}"`
- DLQ writes: `"Request {id} sent to dead letter queue (DLQ #{dlq_id})"`
- Critical failures: `"CRITICAL: Failed to write to dead letter queue"`
- continueOnFail: `"Monthly quick stats failed (continueOnFail)"`
- Admin actions: `"Reservation {id} {action}d by admin"`
- Quarterly reports: `"Quarterly report email requested for {quarter}"`

### 18.4 Audit Trail

Every significant action is recorded in `cgcs.audit_trail`:

| Actor | Actions |
|-------|---------|
| `langgraph_agent` | `agent_evaluated` (with decision, pricing, cost, errors) |
| `admin` | `admin_approved`, `admin_rejected` (with notes, edit flag) |
| `admin` | `checklist_item_updated`, `checklist_bulk_updated` |
| `admin` | `email_rejected_and_reworked`, `revision_selected` |
| `admin` | `quarterly_report_generated` |
| `system` | `quote_generated`, `quote_updated` |

---

## 19. Testing & Evaluation

### 19.1 Test Suite

- **Framework:** pytest + pytest-asyncio + pytest-mock
- **Test count:** 228 passing tests
- **Test files:** 13

| File | Tests | Coverage Focus |
|------|-------|---------------|
| test_api.py | Core | Endpoint routing, auth, request validation, response shapes |
| test_graph.py | Core | Node execution, state transitions, error propagation, conditional edges |
| test_email_triage.py | Email | Ad Astra detection, VIP boosting, auto-send logic, calendar invite detection |
| test_calendar.py | Calendar | Availability check, hold creation, validation errors |
| test_leads.py | Leads | Staff roster validation, monthly cap enforcement, reminder scheduling |
| test_acknowledgment.py | Ack | Template rendering, first-name extraction, endpoint behavior |
| test_checklist.py | Compliance | Checklist generation, conditional items, deadline calculation, bulk updates |
| test_reports.py | Revenue | Revenue aggregation, conversion funnel, CSV export, top orgs |
| test_rejection.py | Email | Rejection storage, rework generation, revision selection, insights |
| test_quotes.py | Quotes | Quote building, versioning, diff tracking, email formatting |
| test_process_insights.py | Analytics | Email/quote/turnaround/compliance metrics, recommendations, endpoints |
| test_labor_rates.py | Constants | Labor rate lookups, staff assignments, prep/breakdown times |
| conftest.py | Shared | Test fixtures for all modules |

### 19.2 Test Fixtures

**File:** `tests/conftest.py`

| Fixture | Description | Key Fields |
|---------|-------------|------------|
| `sample_request` | Valid government agency reservation | Jane Doe, Texas DOE, 2026-04-15, large_conference, 35 attendees |
| `invalid_request` | Request with multiple validation errors | Empty fields, bad date, bad email, end before start |
| `ineligible_request` | Commercial event that should be rejected | Acme Product Co, product launch, 150 attendees |

### 19.3 Running Tests

```bash
PYTHONPATH=langgraph-agent \
  ANTHROPIC_API_KEY=test-key \
  DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test \
  python -m pytest tests/ -v
```

### 19.4 LLM Evaluation (Planned for v3.0)

Currently, LLM output quality is assessed reactively via the rejection-learning system. Planned proactive evaluation:

| Eval Type | What It Checks | Status |
|-----------|---------------|--------|
| **Email quality** | Does the email contain requester's name? Does it mention the date? Is it under 500 words? | Planned |
| **Eligibility accuracy** | Does the decision match known test cases? | Planned |
| **Pricing accuracy** | Does the tier match the organization type? | Planned |
| **Recommendation quality** | Are recommendations specific and actionable (not generic)? | Planned |

---

## 20. Configuration Reference

### 20.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | - | Claude API key |
| `DATABASE_URL` | Yes | - | PostgreSQL connection string (asyncpg format) |
| `LANGGRAPH_API_KEY` | Yes | `""` | Bearer token for admin endpoints |
| `WEBHOOK_SECRET` | Yes | `""` | Shared secret for webhook auth |
| `LOG_LEVEL` | No | `INFO` | Python logging level |
| `ENVIRONMENT` | No | `production` | Environment name (disables /docs in production) |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-20250514` | Claude model identifier |
| `LLM_TIMEOUT` | No | `60` | LLM request timeout (seconds) |
| `LLM_MAX_RETRIES` | No | `3` | LLM retry attempts |
| `LLM_RETRY_BASE_DELAY` | No | `1.0` | Initial retry delay (seconds) |
| `DEAD_LETTER_MAX_FAILURES` | No | `3` | Max DLQ failures before escalation |
| `ADMIN_EMAIL` | No | `""` | Admin notification email |
| `LANGCHAIN_API_KEY` | No | `""` | LangSmith API key |
| `LANGCHAIN_PROJECT` | No | `cgcs-automation` | LangSmith project name |
| `LANGCHAIN_TRACING_V2` | No | `true` | Enable LangSmith tracing |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Conditional | `""` | Path to Google service account JSON |
| `GOOGLE_CALENDAR_ID` | No | `primary` | Google Calendar ID for CGCS events |
| `PET_TRACKER_SPREADSHEET_ID` | Conditional | `""` | Google Sheets ID for P.E.T. tracker |
| `ZOHO_MAIL_TOKEN` | Conditional | `""` | Zoho Mail OAuth token |
| `ZOHO_ACCOUNT_ID` | Conditional | `""` | Zoho account identifier |
| `EMAIL_AUTO_SEND_ALLOWLIST` | No | `stefano.casafrancalaos@austincc.edu,marisela.perez@austincc.edu` | Comma-separated auto-send emails |
| `DOMAIN` | Deployment | - | Base domain for Caddy |
| `ACME_EMAIL` | Deployment | - | Email for ACME TLS certificates |
| `POSTGRES_DB` | Deployment | - | Database name |
| `POSTGRES_USER` | Deployment | - | Database user |
| `POSTGRES_PASSWORD` | Deployment | - | Database password |

---

## 21. Data Flow Diagrams

### 21.1 Event Intake Flow (Updated)

```
Web Form -> N8N Webhook
               |
         POST /api/v1/acknowledge (immediate)
               |
         Check Google Calendar
               |
         POST /api/v1/evaluate
               |
     +-------------------+
     | LangGraph Agent   |
     | validate_input    |
     | evaluate_elig.    |
     | determine_pricing |
     | evaluate_room     |
     | draft_response    |
     +-------------------+
               |
     Save to cgcs.reservations (pending_review)
     Log to cgcs.audit_trail
               |
     Return EvaluateResponse to N8N
               |
     Admin reviews (via API / CGCS Command / LangSmith)
               |
     POST /api/v1/approve/{id}
               |
     +-- Auto-generate quote v1 (continueOnFail)
     +-- Auto-generate checklist (continueOnFail)
     +-- Update cgcs.reservations (approved/rejected)
     +-- Log to cgcs.audit_trail
               |
     N8N sends email to requester via Zoho
```

### 21.2 Email Triage Flow (Updated)

```
N8N Cron (every 5 min)
     |
Poll Zoho Mail (unread inbox)
     |
For each email:
     POST /api/v1/email/triage
          |
    +------------------+
    | LangGraph Agent  |
    | classify_email   |---> Ad Astra? -> auto-classify
    | draft_reply      |---> Calendar? -> skip
    | (+ rejection     |---> VIP? -> boost priority
    |  lessons injected)|
    | check_auto_send  |
    +------------------+
          |
    Allowlisted sender? -> auto-send reply
    Otherwise -> queue for admin review
          |
    Admin: POST /api/v1/email/approve/{id}
      |
      +-- (happy) -> N8N sends reply via Zoho
      |
      +-- (reject) -> POST /api/v1/email/reject-and-rework/{id}
                         |
                    3 improved versions generated
                         |
                    Admin selects or writes custom
                         |
                    POST /api/v1/email/select-revision/{pattern_id}
                         |
                    N8N sends final reply via Zoho
```

### 21.3 Daily Operations Flow (Updated)

```
N8N Cron (8:00 AM CT)
     |
     +-> POST /api/v1/reminders/check
     |        |
     |   find_due_reminders -> send_reminders
     |        |
     |   Send reminder emails via Zoho
     |
     +-> POST /api/v1/daily-digest
              |
         build_daily_digest (9 sections)
         + get_monthly_quick_stats (continueOnFail)
              |
         Send to admin via Zoho
```

### 21.4 Quarterly Report Flow (NEW)

```
Admin or Cron
     |
POST /api/v1/reports/generate-quarterly
     |
+-------------------------------------------+
| process_insights.py                       |
| get_email_metrics()     (email_tasks,     |
|                          rejection_patterns)|
| get_quote_metrics()     (quote_versions)  |
| get_turnaround_metrics()(reservations,    |
|                          audit_trail)      |
| get_compliance_metrics() (event_checklist)|
| get_conversion_funnel()  (reservations)   |
| get_revenue_report()     (reservations)   |
| get_top_organizations()  (reservations)   |
|                                           |
| generate_recommendations() (Claude LLM)  |
+-------------------------------------------+
     |
Return ProcessInsightsResponse
     |
(optional) Send quarterly report email
     |
Log to audit_trail: "quarterly_report_generated"
```

---

## 22. Roadmap — v3.0 Architecture

### 22.1 Composable Agent Architecture

**Current (v2.0):** Monolithic — one FastAPI app, one AgentState, one state machine handling all 12 capabilities.

**Target (v3.0):** Composable — smaller, specialized agents communicating through a message bus or orchestrator.

```
                    [Orchestrator / Message Bus]
                     /    |     |     |     \
              [Intake] [Email] [Calendar] [Reports] [Compliance]
               Agent    Agent    Agent      Agent      Agent
                 \        |       |          |          /
                  +-------+-------+----------+---------+
                              |
                        [PostgreSQL]
```

**Benefits:**
- Each agent has its own focused state (not 90+ fields)
- Independent deployment and scaling
- Failure isolation (email agent crash doesn't affect intake)
- Easier testing (test each agent in isolation)

### 22.2 LLM Output Evaluation Framework

Automated evals that run on every LLM call:

| Eval | Check | Action |
|------|-------|--------|
| Email contains requester name | Regex check against requester_name field | Flag if missing |
| Email mentions date | Regex check for YYYY-MM-DD or month name | Flag if missing |
| Email under word limit | Word count < 500 | Flag if exceeded |
| Eligibility matches known cases | Compare against curated test dataset | Alert on divergence |
| Pricing tier matches org type | Rule-based check against known org mappings | Alert on mismatch |
| Recommendations are specific | Check for concrete numbers/percentages | Flag if generic |

### 22.3 Guardrails Layer

Schema validation and content filtering on all LLM responses:

- **Schema validation**: Pydantic models for every LLM output format (not just try/except on JSON)
- **Content filtering**: Check generated emails for prohibited content (pricing before approval, unauthorized commitments)
- **Hallucination detection**: Verify that LLM-generated facts match the input data (dates, names, amounts)

### 22.4 CGCS Command Dashboard

Purpose-built admin dashboard (see Section 12.4).

---

## Appendices

### A. Glossary

| Term | Definition |
|------|------------|
| CGCS | Center for Government & Civic Service at Austin Community College |
| AMI | Austin Meeting & Innovation (facility pricing model for paid events) |
| P.E.T. | Program Event Tracker (Google Sheets-based operational tracker) |
| DLQ | Dead Letter Queue (failed request recovery system) |
| N8N | Open-source workflow automation platform (trigger/orchestration layer) |
| TDX | TeamDynamix (ACC's AV request system) |
| AAIS | Ad Astra Information Systems (room scheduling platform) |
| ACC | Austin Community College |
| CT | Central Time (America/Chicago) |
| HITL | Human-in-the-Loop |
| continueOnFail | Error handling pattern where failure is logged but doesn't block the main flow |

### B. Contact Information

| Role | Name | Email | Notes |
|------|------|-------|-------|
| CGCS Admin (personal) | Austin Wells | austin.wells@austincc.edu | ACC work email — digest recipient, not system email |
| CGCS System Email (current) | Admin | admin@cgcsacc.org | Zoho Mail — LEGACY, being retired |
| CGCS System Email (future) | Admin | admin@cgcs-acc.org | Google Workspace — primary system email going forward |
| Zoho User ID | - | 879105889 | LEGACY — will be retired with Zoho migration |

### B.1 Email & Account Architecture

**Current state:**
- Intake form submissions → received by Zoho Mail at `admin@cgcsacc.org`
- Outbound emails to requesters → sent via Zoho Mail API from `admin@cgcsacc.org`
- Daily digest → sent to Austin's personal work email (`austin.wells@austincc.edu`)
- GitHub repo → under personal account `austinwells-pixel/cgcs-automation`

**Target state:**
- Intake form submissions → received by Google Workspace at `admin@cgcs-acc.org`
- Outbound emails → sent via Gmail API from `admin@cgcs-acc.org`
- Daily digest → sent to `admin@cgcs-acc.org` (organizational inbox)
- GitHub repo → under organization account `cgcs-acc/cgcs-automation`

**Migration plan:**

| Step | Action | Status |
|------|--------|--------|
| 1 | Purchase Google Workspace (`admin@cgcs-acc.org`) | Done |
| 2 | Create GitHub organization (`cgcs-acc`) | Pending (payment processing) |
| 3 | Transfer repo from `austinwells-pixel` to `cgcs-acc` org | Pending |
| 4 | Add coworker as GitHub org owner | Pending |
| 5 | Point intake form webhook to `admin@cgcs-acc.org` | Pending |
| 6 | Replace Zoho Mail integration with Gmail API | Pending |
| 7 | Update `ADMIN_EMAIL` to organizational email | Pending |
| 8 | Update Google Calendar service account under Workspace | Pending |
| 9 | Retire Zoho Mail account | Pending |

**Why this matters for continuity:**
- `@austincc.edu` emails are tied to individual employees — they leave when the person leaves
- `admin@cgcs-acc.org` is organizational — it survives staff turnover
- GitHub org ensures the repo doesn't live under anyone's personal account
- The SOP reduces to: "here's the org login, here's the .env on the server"

**Developer accounts (personal, non-transferable — by design):**
- Claude Code — each developer uses their own account
- LangSmith — each developer uses their own login
- GitHub — contributors use personal accounts, org owns the repo

### C. External URLs

| Resource | URL |
|----------|-----|
| CGCS Website | https://www.cgcsacc.org |
| TDX AV Portal | https://acchelp.austincc.edu/TDClient/277/Portal/Requests/ServiceDet?ID=10656 |

### D. Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0 | 2026-03-02 | Initial technical specification (8 capabilities, 19 endpoints, 96 tests) |
| 2.0 | 2026-03-03 | Added 6 capability modules, labor rates, LangSmith HITL architecture, composable agent roadmap, email/account migration plan from Zoho to Google Workspace (12 capabilities, 38 endpoints, 228 tests) |

---

*This document is the authoritative technical reference for the CGCS Unified Agent system. For operational procedures and user guides, see the README.md. For the previous version, see TECHNICAL_SPECIFICATION_v1.0.md.*
