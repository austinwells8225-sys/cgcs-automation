# CGCS Unified Agent — Technical Specification

**Version:** 3.0
**Date:** 2026-04-22
**System:** CGCS Event Space Automation Engine
**Organization:** Center for Government & Civic Service (CGCS), Austin Community College
**Admin:** Austin Wells, Strategic Planner for Community Relations & Environmental Affairs
**Launch Target:** 2026-04-27 (Monday)

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
22. [User Agreements](#22-user-agreements)
23. [Launch Status & Punch List](#23-launch-status--punch-list)
24. [Roadmap — v4.0 Architecture](#24-roadmap--v40-architecture)
25. [Appendices](#appendices)

---

## 1. Executive Summary

The CGCS Unified Agent is a production-deployed AI automation platform for the Center for Government & Civic Service at Austin Community College. Built on LangGraph, it is a unified state machine that routes **14 distinct AI-powered capabilities** through a single FastAPI application backed by Claude (Anthropic).

As of v3.0, the system is **deployed to production** on a Hetzner VPS via Coolify, with a Gmail-based inbox poller running inside the FastAPI process to pull Smartsheet intake notifications every 5 minutes. The system processes event space reservations, email triage (with self-improving drafts), calendar management, calendar holds with 28-field CGCS entry templates, event lead assignments, reminders, P.E.T. tracking, compliance checklists, revenue tracking, dynamic quote versioning, process insights with AI-powered recommendations, daily digests, and Smartsheet intake classification — all with **human-in-the-loop approval gates** ensuring no outbound communication reaches external parties without explicit admin approval.

### Key Metrics

| Metric | v1.0 | v2.0 | v3.0 |
|--------|------|------|------|
| Capability subgraphs | 8 | 12 | 14 |
| FastAPI endpoints | 19 | 38 | 44 |
| PostgreSQL tables | 8 | 11 | 12 |
| Migrations | 3 | 9 (001–009) | 10 (001–010) |
| Test suite | 96 | 228 passing | 604 passing, 0 failures |
| AgentState fields | 82 | 90+ | 110+ |
| Pydantic request/response models | 16 | 40+ | 50+ |
| LLM system prompts | 5 | 8 | 14 |
| Services modules | 3 | 5 | 9 |
| Database query modules | 6 | 9 | 10 |
| Graph nodes | 14 | 21+ | 25+ |

### What Changed from v2.0 to v3.0

| Area | Change |
|------|--------|
| **Deployment** | From theoretical Docker Compose to live Hetzner VPS (46.225.111.82) deployed via Coolify v4 with GitHub App auto-deploy |
| **Email provider** | Zoho Mail fully retired; Gmail API on `admin@cgcs-acc.org` (Google Workspace) is the exclusive system email |
| **Email monitoring** | ADR-001 executed: moved email ingestion from n8n polling to in-agent APScheduler (`smartsheet_inbox_poller.py` + `scheduler.py`) |
| **New capability** | Smartsheet intake classification (`smartsheet_intake` task type) — parses Smartsheet notification emails, classifies as easy/mid/hard, drafts replies, creates calendar HOLDs with 28-field descriptions |
| **Gmail drafts** | New `create_draft` and `create_draft_reply` functions — agent saves drafts to Gmail Drafts threaded to original messages rather than sending blind |
| **OAuth scopes** | Migrated from broad `https://mail.google.com/` to specific four-scope list (readonly, modify, compose, send) to align with Google Workspace Domain-Wide Delegation allowlist |
| **Calendar entry template** | Formalized 28-field template for HOLD descriptions; `build_calendar_hold()` auto-populates from parsed Smartsheet data |
| **Gmail filter bridge** | `austin.wells@austincc.edu` auto-forwards matching Smartsheet notifications to `admin@cgcs-acc.org` to bypass ACC firewall intermittent blocks |
| **User agreements** | Both Internal and External user agreements fully revised and finalized (aligned lead times, $300 cleanup fee, new Cancellation and Liability sections, removed deprecated contacts) |
| **Pricing framework** | April 2026 revision: new Main Hall tiers ($625/$1,200/$1,500), tiered discounts for nonprofits/government/recurring clients, AV Basic flat $160 |
| **Repository** | Moved to `austinwells8225-sys/cgcs-automation` on GitHub with Coolify auto-deploy via GitHub App |

---

## 2. System Overview

### 2.1 Purpose

The CGCS manages event space at Austin Community College's Rio Grande Campus (RGC Building 3000). Prior to this system, all intake processing — eligibility evaluation, pricing, calendar checks, email responses, and operational tracking — was performed manually by the CGCS administrator. This system automates those workflows while preserving human oversight at critical decision points.

### 2.2 Core Principles

1. **Human-in-the-loop**: No outbound email reaches a requester without admin approval (except for an explicit auto-send allowlist of 2 internal staff members).
2. **Draft-first, never send blind**: On Smartsheet intake, the agent saves a threaded Gmail Draft — admin reviews and sends from Gmail directly.
3. **Never drop a request**: Failed graph executions are captured in a dead letter queue for manual recovery. No request is ever silently lost.
4. **Retry resilience**: All LLM calls and external HTTP requests retry 3x with exponential backoff.
5. **Input sanitization**: All user-supplied strings are stripped of control characters, collapsed of excessive whitespace, and truncated to 5,000 characters.
6. **Single state machine**: One `AgentState` TypedDict carries all data through the graph, with task_type-based routing selecting the correct subgraph.
7. **Auditability**: Every state transition and admin action is logged to an audit trail with actor identity and JSONB details.
8. **continueOnFail**: Non-critical operations (auto-quote generation, monthly stats, calendar hold creation) never block the main flow. Failures are logged but execution continues.
9. **Self-improving**: Rejection patterns are stored and fed back into future prompts, so the system learns from admin corrections over time.
10. **Email ingestion lives in the agent** (ADR-001): rather than depending on n8n cron to poll Zoho, the agent runs its own APScheduler-driven Gmail poller inside the FastAPI lifespan. Simpler operational model, fewer failure surfaces.

### 2.3 Users

| Role | Description | Authentication |
|------|-------------|---------------|
| External Requester | Submits event space reservation requests via Smartsheet form or direct email | None (form processed by Smartsheet) |
| Internal ACC Requester | Books Ad Astra + fills Event and Room Rentals form on cgcsacc.org | ACC SSO (on external form platform) |
| CGCS Admin | Reviews, approves/rejects reservations and email drafts | Gmail Drafts (review + send), LangSmith (API key), CGCS Command dashboard (planned) |
| Coolify Deploy | GitHub push triggers deploy | GitHub App + Coolify webhook |
| n8n Webhooks | Retained for admin approval + reminder cron triggers | Webhook shared secret |
| Internal API Consumers | Admin endpoints for lead assignment, P.E.T. tracker, etc. | Bearer API key |

---

## 3. Architecture

### 3.1 High-Level Architecture

```
                          Internet
                             |
                     [sslip.io DNS]
                             |
                    [Coolify Edge Proxy]
                       (auto-HTTPS)
                       /           \
                [N8N:5678]    [Agent:8000]
               (triggers only)     |
                                   +---> [LangSmith] (observability + HITL)
                                   +---> [Gmail API] (admin@cgcs-acc.org via DWD)
                                   +---> [Google Calendar API]
                                   +---> [Google Sheets API] (P.E.T.)
                                   +---> [Anthropic Claude API]
                                   |
                             [PostgreSQL:5432]
                                   |
                             [cgcs schema]
                                   |
                          [Hetzner VPS CPX22]
                        Ubuntu 24.04 / 46.225.111.82
```

### 3.2 Deployment Topology

| Component | Location | Details |
|-----------|----------|---------|
| **Production host** | Hetzner Cloud VPS | CPX22 instance, Ubuntu 24.04, IP 46.225.111.82 |
| **Deployment platform** | Coolify v4 | Self-hosted PaaS, manages all containers, handles deploys |
| **Git integration** | GitHub App | Push to `main` triggers Coolify build + deploy |
| **Repository** | GitHub | `austinwells8225-sys/cgcs-automation` |
| **Container runtime** | Docker | Orchestrated by Coolify via docker-compose under the hood |
| **Public access** | sslip.io | Wildcard DNS for convenient HTTPS without owning a domain |
| **Live n8n webhook** | `http://h26cllcwo5xtb6yaszqjdxkv.46.225.111.82.sslip.io/webhook/intake/event-space` | Receives Smartsheet + external events |
| **Coolify admin** | `http://46.225.111.82:8000` | Internal admin UI |
| **Agent API (internal)** | `http://langgraph-agent:8000` (inside Docker network) | Direct container-to-container |

### 3.3 Component Architecture

```
FastAPI Application (app/main.py)
    |
    +-- 44 API Endpoints
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
    |     |- Staff Roster (API key auth)
    |     |- **Smartsheet Polling (API key auth) — NEW in v3.0**
    |     |- **Scheduler Status (API key auth) — NEW in v3.0**
    |     +- Email Reply Processing (webhook secret auth) — NEW in v3.0
    |
    +-- LangGraph State Machine (graph/)
    |     |- StateGraph(AgentState)
    |     |- 25+ Nodes across 13 modules
    |     |- 8 Conditional Edge Functions
    |     +- Router pattern: route_task -> subgraph (14 task types)
    |
    +-- Services (services/)
    |     |- gmail_service.py — Gmail API (409 lines, including create_draft + create_draft_reply)
    |     |- google_calendar.py — Google Calendar API (check, create hold, get_alternative_dates)
    |     |- google_sheets.py — Google Sheets API (read, stage, apply)
    |     |- smartsheet_parser.py — Parses Smartsheet notification emails
    |     |- smartsheet_inbox_poller.py — APScheduler-driven Gmail inbox poller (NEW)
    |     |- scheduler.py — APScheduler AsyncIOScheduler (NEW)
    |     |- intake_classifier.py — Smartsheet intake classification + draft templates
    |     |- intake_processor.py — Room formatters, calendar hold builder, P.E.T. row builder
    |     |- quote_builder.py — Pure-function quote generation
    |     |- process_insights.py — Analytics queries & AI recommendations
    |     +- reply_processor.py — Inbound email reply classification
    |
    +-- In-Process Scheduler (NEW in v3.0)
    |     |- AsyncIOScheduler instance
    |     |- Runs inside FastAPI lifespan
    |     |- Jobs: smartsheet_inbox_poll (every 5 min by default)
    |     |- Timezone: America/Chicago
    |     +- Hot-configurable via SMARTSHEET_POLL_* env vars
    |
    +-- Database Layer (db/)
    |     |- asyncpg connection pool (2-10 connections)
    |     |- 10 query modules
    |     +- PostgreSQL 16 with cgcs schema (12 tables)
    |
    +-- Business Logic
    |     |- data/ — Pricing tiers, room configs, eligibility
    |     |- cgcs_constants.py — Staff, deadlines, labor rates, 28-field calendar template, P.E.T. columns
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
          |- Process recommendations prompt
          |- Smartsheet intake easy-response template (NEW)
          |- Smartsheet intake review-response template (NEW)
          |- Furniture coordination email template (NEW)
          |- Police coordination email template (NEW)
          |- Internal vs External reply branching rules (NEW)
          +- Rejection lessons injection format (NEW)
```

### 3.4 Graph Architecture (State Machine)

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
  |-- smartsheet_intake: (NEW in v3.0)
  |     classify_intake_request -> create_hold_from_intake -> draft_intake_emails -> END
  |     (creates HOLD on Google Calendar with 28-field description)
  |     (drafts main reply + furniture/police coordination emails if needed)
  |     (continueOnFail: hold creation failure does NOT abort drafting)
  |
  |-- email_triage:
  |     classify_email -> draft_email_reply -> check_auto_send -> END
  |     (rejection: store pattern, generate 3 improved versions)
  |
  |-- email_reply: (NEW in v3.0)
  |     process_email_reply -> END
  |     (classifies inbound reply, updates edit loop counter, detects escalations,
  |      detects furniture change requests)
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
| AI Model | Claude (Anthropic) | `claude-sonnet-4-20250514` or later | LLM for eligibility, pricing, email triage, drafting, recommendations |
| Agent Framework | LangGraph | 0.3.x | State machine graph execution |
| LLM Integration | LangChain Anthropic | 0.3.x | Claude API wrapper with message formatting |
| Web Framework | FastAPI | 0.115.x | REST API with automatic OpenAPI docs |
| ASGI Server | Uvicorn | 0.34.x | Production ASGI server |
| **In-process scheduler** | **APScheduler** | **3.10.x (NEW)** | **AsyncIOScheduler for Gmail inbox polling** |
| Database | PostgreSQL | 16-alpine | Primary data store |
| DB Driver | asyncpg | 0.30.x | Async PostgreSQL driver |
| Data Validation | Pydantic | 2.10.x | Request/response models, settings |
| Settings | pydantic-settings | 2.7.x | Environment-based configuration |
| HTTP Client | httpx | 0.28.x | External API calls (Google, Anthropic) |
| Google Auth | google-auth | 2.x | Service account + DWD impersonation |
| Observability | LangSmith | 0.2.x | LLM trace collection + human-in-the-loop review |
| Orchestration | n8n | latest | Retained for webhook triggers (5 workflows) |
| Deployment platform | Coolify | v4 | Self-hosted PaaS on Hetzner |
| Containerization | Docker / Docker Compose | - | 4-service deployment |
| Host OS | Ubuntu | 24.04 | Hetzner VPS base |
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
apscheduler>=3.10,<4  # NEW in v3.0
```

### 4.2 Environment Architecture (NEW in v3.0)

The Hetzner VPS runs a Coolify instance. Coolify manages a `docker-compose` stack with the following services:

| Service | Container | Image | Internal Port | Public Access |
|---------|-----------|-------|---------------|---------------|
| FastAPI Agent | `langgraph-agent` | Custom (Dockerfile in `langgraph-agent/`) | 8000 | via Coolify edge proxy |
| n8n | `n8n` | `n8nio/n8n:latest` | 5678 | via sslip.io URL |
| PostgreSQL | `postgres` | `postgres:16-alpine` | 5432 | internal only |
| Coolify edge proxy | `coolify-proxy` | Coolify-managed | 80, 443 | yes |

**Known infrastructure issue:** Coolify edge proxy currently returns 504 Gateway Timeout when routing to the langgraph-agent container from outside the host. Direct container-to-container routing works (e.g., the in-process poller calling Gmail API works fine). Not blocking for the pull-based intake path since that's internal to the agent. Needs resolution before external integrations can call the agent directly.

---
## 5. Project Structure

```
ai-intake/
├── langgraph-agent/
│   ├── Dockerfile                          # Python 3.12-slim, non-root user
│   ├── requirements.txt                    # Pinned dependency ranges (apscheduler NEW)
│   └── app/
│       ├── main.py                         # FastAPI app, 44 endpoints, lifespan mgmt (now includes scheduler startup)
│       ├── config.py                       # Pydantic Settings (32+ env vars, Smartsheet poller vars NEW)
│       ├── models.py                       # 50+ Pydantic request/response models
│       ├── cgcs_constants.py               # Staff roster, pricing, deadlines, labor rates, 28-field calendar template, P.E.T. columns, checklist
│       ├── prompt_tuning.py                # Self-improving prompt lessons from rejection patterns
│       ├── graph/
│       │   ├── state.py                    # AgentState TypedDict (110+ fields, smartsheet_* fields NEW)
│       │   ├── builder.py                  # StateGraph construction (25+ nodes)
│       │   ├── edges.py                    # 8 conditional routing functions (after_intake_classification NEW)
│       │   └── nodes/
│       │       ├── __init__.py             # Re-exports all node functions
│       │       ├── router.py               # Task-type validation & routing (now 14 valid types)
│       │       ├── intake.py               # Event intake: validate, eligibility, pricing, room, draft (7 nodes)
│       │       ├── email_triage.py         # Email: classify, draft, auto-send (3 nodes)
│       │       ├── email_reply.py          # NEW: process_email_reply
│       │       ├── calendar.py             # Calendar availability check (1 node)
│       │       ├── calendar_hold.py        # Calendar hold: validate, create (2 nodes)
│       │       ├── smartsheet_intake.py    # NEW: classify_intake_request, create_hold_from_intake, draft_intake_emails
│       │       ├── pet_tracker.py          # P.E.T.: read, prepare update (2 nodes)
│       │       ├── event_lead.py           # Event leads: assign, schedule reminders (2 nodes)
│       │       ├── reminders.py            # Reminders: find due, send (2 nodes)
│       │       ├── daily_digest.py         # Daily digest builder (1 node, 9 sections)
│       │       └── shared.py               # LLM client, retry logic, sanitization
│       ├── services/
│       │   ├── gmail_service.py            # Gmail API (409 lines — create_draft + create_draft_reply NEW)
│       │   ├── google_calendar.py          # Google Calendar API (check, create hold, get_alternative_dates)
│       │   ├── google_sheets.py            # Google Sheets API (read, stage, apply)
│       │   ├── smartsheet_parser.py        # Parses Smartsheet notification emails into structured dict
│       │   ├── smartsheet_inbox_poller.py  # NEW (190 lines) — APScheduler-driven Gmail inbox poller
│       │   ├── scheduler.py                # NEW (101 lines) — APScheduler AsyncIOScheduler
│       │   ├── intake_classifier.py        # 429+ lines — classify_request + draft templates (easy/review) + furniture/police emails
│       │   ├── intake_processor.py         # Room formatters, build_calendar_hold (28 fields), build_pet_row
│       │   ├── reply_processor.py          # Inbound reply classification + edit loop tracking
│       │   ├── quote_builder.py            # Pure-function quote generation (zero DB deps)
│       │   └── process_insights.py         # Analytics queries & AI recommendations
│       ├── db/
│       │   ├── connection.py               # asyncpg pool management (2-10 connections)
│       │   ├── queries.py                  # Reservation CRUD, audit trail, DLQ
│       │   ├── email_queries.py            # Email task CRUD
│       │   ├── lead_queries.py             # Event lead & reminder CRUD
│       │   ├── hold_queries.py             # Calendar hold CRUD
│       │   ├── pet_queries.py              # P.E.T. staged update CRUD
│       │   ├── checklist_queries.py        # Compliance checklist CRUD & reports
│       │   ├── rejection_queries.py        # Email rejection pattern CRUD
│       │   ├── quote_queries.py            # Quote version CRUD
│       │   ├── report_queries.py           # Revenue & reporting queries
│       │   └── smartsheet_queries.py       # NEW: Smartsheet intake tracking
│       ├── prompts/
│       │   └── templates.py                # 14 Claude system prompts
│       └── data/
│           ├── pricing.py                  # 5 pricing tiers + April 2026 revised tiers
│           ├── room_setup.py               # 5 room configs, auto-assignment
│           └── eligibility.py              # Eligibility rules & exclusions
├── db/
│   ├── init.sql                            # Schema bootstrap (CREATE SCHEMA cgcs)
│   └── migrations/
│       ├── 001_initial_schema.sql          # Core tables
│       ├── 002_seed_data.sql               # Pricing tiers & room configurations
│       ├── 003_multi_capability.sql        # Email, leads, reminders, holds, P.E.T. tables
│       ├── 004_placeholder.sql             # Reserved
│       ├── 005_revenue_columns.sql         # Revenue columns on reservations
│       ├── 006_placeholder.sql             # Reserved
│       ├── 007_event_checklist.sql         # Compliance checklist table
│       ├── 008_rejection_patterns.sql      # Email rejection patterns table
│       ├── 009_quote_versions.sql          # Quote versioning table
│       └── 010_smartsheet_tracking.sql     # NEW: Smartsheet intake tracking table
├── n8n-workflows/                          # JSON exports for reproducibility
│   ├── event-space-intake.json             # Webhook: form submission
│   ├── admin-approval.json                 # Webhook: admin approve/reject (pending publish)
│   ├── reminder-cron.json                  # Cron: 8am CT daily digest (pending publish)
│   └── calendar-hold.json                  # Manual trigger (legacy, less used now)
├── docs/                                   # NEW in v3.0 — in-repo documentation
│   └── ADR-001-email-monitoring.md         # ADR: moving email ingestion into agent (pending commit)
├── tests/                                  # 604 tests, 0 failures
│   ├── conftest.py                         # Shared test fixtures
│   ├── test_api.py                         # Core endpoint tests
│   ├── test_graph.py                       # Graph execution, state transitions
│   ├── test_email_triage.py                # Email: Ad Astra, VIP, auto-send, calendar invite
│   ├── test_calendar.py                    # Calendar availability + hold
│   ├── test_leads.py                       # Lead assignment, monthly cap
│   ├── test_acknowledgment.py              # Auto-ack template
│   ├── test_checklist.py                   # Compliance checklist
│   ├── test_reports.py                     # Revenue, conversion funnel, CSV export
│   ├── test_rejection.py                   # Email rejection & rework
│   ├── test_quotes.py                      # Quote versioning
│   ├── test_process_insights.py            # Analytics & recommendations
│   ├── test_labor_rates.py                 # Labor rate constants
│   ├── test_smartsheet_intake.py           # NEW: parser, classifier, draft templates
│   ├── test_smartsheet_poller.py           # NEW: Gmail poller, threading, marking read
│   ├── test_scheduler.py                   # NEW: APScheduler lifecycle
│   └── test_email_reply.py                 # NEW: reply classifier, edit loop, escalations
├── caddy/                                  # (Superseded by Coolify edge proxy; config retained for reference)
│   └── Caddyfile
├── TECHNICAL_SPECIFICATION_v3_0.md         # This document
└── README.md                                # Operational runbook
```

---

## 6. State Machine & Graph Engine

### 6.1 AgentState TypedDict

The entire system operates on a single TypedDict that carries all data through the graph. Fields are namespaced by capability using optional typing (`total=False`).

**File:** `langgraph-agent/app/graph/state.py`

| Field Group | Fields | Purpose |
|-------------|--------|---------|
| **Common** (7) | `task_type`, `request_id`, `errors`, `decision`, `draft_response`, `requires_approval`, `approved` | Routing, tracking, approval gate |
| **Event Intake** (16) | Full reservation pipeline | See v2.0 spec for details |
| **Email Triage** (8) | Email classification & response | See v2.0 spec for details |
| **Calendar Check** (5) | Availability queries | See v2.0 spec for details |
| **Calendar Hold** (7) | `hold_org_name`, `hold_date`, `hold_start_time`, `hold_end_time`, `hold_event_id`, `hold_event_type`, `hold_html_link` **(NEW)** | Hold creation + link back for reference |
| **P.E.T. Tracker** (4) | Spreadsheet operations | See v2.0 spec for details |
| **Event Lead** (5) | Staff assignment | See v2.0 spec for details |
| **Reminders** (2) | Notification scheduling | See v2.0 spec for details |
| **Daily Digest** (10) | Admin summary with 9 sections + intern leads | See v2.0 spec for details |
| **Event Type** (1) | `event_type` | S-EVENT, C-EVENT, A-EVENT classification |
| **Quote** (1) | `quote_email_snippet` | For embedding in approval emails |
| **Smartsheet Intake** (4) — NEW | `smartsheet_parsed`, `intake_classification`, `intake_difficulty`, `intake_draft_emails` | Smartsheet flow state |
| **Email Reply / Conversation** (10) — NEW | `reply_body`, `edit_loop_count`, `failed_replies`, `escalation_detected`, `escalation_reasons`, `escalation_forward_to`, `furniture_changes_detected`, `furniture_change_descriptions`, `reply_draft_emails`, `reply_alerts`, `reply_action` | Inbound reply processing |

### 6.2 Graph Construction

**File:** `langgraph-agent/app/graph/builder.py`

The graph is built using LangGraph's `StateGraph` API with 25+ nodes and 8 conditional edge functions.

**New nodes in v3.0:**

| Node | Module | LLM Call | Description |
|------|--------|----------|-------------|
| `classify_intake_request` | smartsheet_intake.py | No | Runs `classify_request(parsed)` → easy/mid/hard + flags |
| `create_hold_from_intake` | smartsheet_intake.py | No | Builds 28-field description via `build_calendar_hold(parsed)`, creates HOLD on Google Calendar, stashes `hold_event_id` + `hold_html_link` |
| `draft_intake_emails` | smartsheet_intake.py | No* | Calls `draft_intake_response()` + optional `draft_furniture_email()` + `draft_police_email()` |
| `process_email_reply` | email_reply.py | Yes | Classifies inbound reply, updates state, flags escalations |

*The `draft_intake_response()` function currently uses deterministic templates (not LLM). Post-launch roadmap adds LLM drafting with voice corpus; template remains as fallback.

### 6.3 Router — Valid Task Types (NEW: 14 total)

**File:** `langgraph-agent/app/graph/nodes/router.py`

```python
VALID_TASK_TYPES = {
    "event_intake",
    "smartsheet_intake",    # NEW in v3.0
    "email_triage",
    "email_reply",          # NEW in v3.0
    "calendar_check",
    "calendar_hold",
    "pet_tracker",
    "event_lead",
    "reminder_check",
    "daily_digest",
}
```

**Critical router fix (commit `91cc41e`, 2026-04-20):** `smartsheet_intake` was missing from `VALID_TASK_TYPES` despite being mapped in `edges.py`, causing all Smartsheet-driven graph invocations to fall through to the manual-review fallback. Fixed by adding the entry.

### 6.4 Conditional Edge Functions (8)

| Function | Source Node | New / Changed |
|----------|-------------|---------------|
| `after_routing` | route_task | Updated for 14 task types |
| `after_validation` | validate_input | Unchanged |
| `after_eligibility` | evaluate_eligibility | Unchanged |
| `after_email_classification` | classify_email | Unchanged |
| `after_hold_validation` | validate_hold_request | Unchanged |
| `after_pet_read` | read_pet_tracker | Unchanged |
| `after_lead_assignment` | assign_event_lead | Unchanged |
| **`after_intake_classification`** | **classify_intake_request** | **NEW in v3.0** — routes to `create_hold_from_intake` (happy path) or `handle_error` |

---

## 7. Capability Specifications

### 7.1 Event Intake

Unchanged from v2.0. See v2.0 specification for validation rules, eligibility evaluation, pricing determination, room setup, and post-approval side effects.

### 7.2 Automatic Acknowledgment Emails

Unchanged from v2.0. Template in `cgcs_constants.py` now points to `admin@cgcs-acc.org` (not `admin@cgcsacc.org`).

### 7.3 Smartsheet Intake (NEW in v3.0)

**Task type:** `smartsheet_intake`
**Trigger:** In-process APScheduler poller (every 5 min default) + `POST /api/v1/smartsheet/poll-now` (manual)
**Auth:** Scheduler is internal; manual endpoint uses API key
**LLM calls:** 0 (uses deterministic templates; LLM drafting is a post-launch roadmap item)

**Pipeline:**

```
classify_intake_request -> create_hold_from_intake -> draft_intake_emails -> END
```

**Step 1 — classify_intake_request:**
- Reads `state["smartsheet_parsed"]` (dict of parsed Smartsheet fields)
- Runs `classify_request(parsed)` in `intake_classifier.py`
- Returns classification: `difficulty` (easy/mid/hard), `confidence` (0-1), `reasoning`, plus flags:
  - `is_external`: derived from Request Type field
  - `requires_furniture_email`: TRUE if furniture items requested
  - `requires_police`: TRUE if weekend/evening event (auto per hours-of-operation rules)
  - `requires_av_tdx`: TRUE if A/V requested (requires TDX ticket)
  - `is_vip`: TRUE if Michelle Raymond or Office of the Chancellor
  - `has_walkthrough_request`: TRUE if walk-through requested

**Step 2 — create_hold_from_intake:**
- Extracts event name, date, times from parsed
- Builds 28-field description via `build_calendar_hold(parsed)` (see §13.14)
- Builds title via `build_calendar_title("HOLD", event_name)` → `"HOLD - {event_name}"`
- Calls `google_calendar.create_hold()` — creates HOLD event on CGCS Events calendar with banana yellow color (colorId: 5)
- Returns `hold_event_id` + `hold_html_link` into state
- **continueOnFail:** if hold creation fails, logs error, appends to `state["errors"]`, but does NOT abort the flow. Drafting still happens.

**Step 3 — draft_intake_emails:**
- Calls `draft_intake_response(parsed, classification)` → main reply draft
  - For `easy` classification: short confirmation draft with next steps
  - For `mid`/`hard`: detailed draft that surfaces coordination flags ("weekend event — police coordination required", "A/V requested — TDX ticket needed")
- Calls `draft_furniture_email(parsed)` if furniture requested → coordination draft to Tyler Briery + Scott Farmer
- Calls `draft_police_email(parsed)` if police needed → coordination draft to James Ortiz
- Returns list of drafts in state for the poller to save to Gmail Drafts

**Draft template anatomy (post commit `e204242`, 2026-04-21):**
- Honest about hold status (references `hold_event_id` when present, says "reviewing availability" when not)
- Mentions requested room name (e.g., "CGCS Main Hall (RGC3.3340)")
- Surfaces classification flags in review responses
- Signs as "CGCS Team" with `admin@cgcs-acc.org` and `www.cgcsacc.org`
- No placeholder link to the public marketing site mislabeled as "calendar"

**Auto-send logic:**
- If requestor email is on the auto-send allowlist (`stefano.casafrancalaos@austincc.edu`, `marisela.perez@austincc.edu`), `auto_send: True` is set
- Currently the poller **never** sends automatically — always saves to Gmail Drafts. Auto-send is a roadmap item.

### 7.4 Smartsheet Inbox Poller (NEW in v3.0)

**File:** `langgraph-agent/app/services/smartsheet_inbox_poller.py` (190 lines)
**Scheduler driver:** `langgraph-agent/app/services/scheduler.py` (101 lines)

**Lifecycle:**
1. FastAPI lifespan event starts the APScheduler `AsyncIOScheduler`
2. Scheduler registers one job: `poll_smartsheet_inbox(compiled_graph)` every `SMARTSHEET_POLL_MINUTES` minutes (default 5)
3. Timezone: `America/Chicago`
4. On shutdown, scheduler stops cleanly

**Polling flow:**
1. Query Gmail via service account (impersonating `admin@cgcs-acc.org`):
   ```
   is:unread from:@app.smartsheet.com subject:"Notice of Event Space Request"
   ```
2. For each matching email (max `SMARTSHEET_POLL_MAX_EMAILS` per cycle, default 10):
   a. Parse subject + body via `smartsheet_parser.parse_smartsheet_intake()` → structured dict
   b. Invoke graph with `{"task_type": "smartsheet_intake", "smartsheet_parsed": parsed}`
   c. Collect draft emails from graph result
   d. For each draft: call `gmail_service.create_draft_reply()` → saves threaded Gmail Draft
   e. Mark original email as read so next cycle skips it
3. Return `{"checked": N, "processed": N, "skipped": N, "errors": [...]}`

**Gmail filter bridge (required for ACC-sourced emails):**
Smartsheet notifications go to `austin.wells@austincc.edu` by default (since the form owner is Brian McElligott and Austin is Editor, not Admin). ACC's email security occasionally blocks emails addressed to `admin@cgcs-acc.org`. To work around this:
- A Gmail filter on `austin.wells@austincc.edu` matches `from:@app.smartsheet.com subject:"Notice of Event Space Request"` and auto-forwards to `admin@cgcs-acc.org`
- The poller on `admin@cgcs-acc.org` sees the forwarded email and processes it

**Long-term fix (post-launch):** Pitch Brian McElligott + Michelle Raymond to add `admin@cgcs-acc.org` directly as a Smartsheet notification recipient, removing the forwarding hop.

**Configuration env vars:**

| Variable | Default | Description |
|----------|---------|-------------|
| `SMARTSHEET_POLL_ENABLED` | `true` | Master toggle |
| `SMARTSHEET_POLL_MINUTES` | `5` | Poll interval in minutes |
| `SMARTSHEET_POLL_MAX_EMAILS` | `10` | Max emails processed per cycle |
| `GMAIL_DELEGATED_USER` | `admin@cgcs-acc.org` | User to impersonate via DWD |

**Key endpoints:**
- `POST /api/v1/smartsheet/poll-now` — manually trigger one poll cycle (useful for testing + debugging)
- `GET /api/v1/smartsheet/scheduler-status` — lists registered jobs + next scheduled run times

### 7.5 Email Triage

Unchanged from v2.0 in mechanics. Two material updates:
- Provider swapped from Zoho Mail to Gmail API
- VIP rule formalized: `michelle.raymond@austincc.edu` or "Office of the Chancellor" in subject → high priority + escalation email to Michelle + admin@cgcs-acc.org + austin.wells@austincc.edu

### 7.6 Email Reply Processing (NEW in v3.0)

**Task type:** `email_reply`
**Trigger:** Graph invocation by email triage flow when classified as `intake_followup` or `follow_up`
**LLM calls:** 1 (classification of reply intent)

**Pipeline:**
```
process_email_reply -> END
```

**Functions:**
- Increments `edit_loop_count` (caps at 10 per original thread to prevent runaway back-and-forth)
- Detects escalation triggers: legal language, explicit complaint, request for supervisor
- Detects furniture change requests: "add X tables", "change layout to Y"
- On escalation: auto-drafts forward email to Michelle Raymond + admin@cgcs-acc.org + austin.wells@austincc.edu
- On furniture change: auto-drafts notification to Tyler Briery + Scott Farmer

### 7.7 Calendar Operations

Unchanged from v2.0.

### 7.8 Calendar Hold — 28-Field Template (NEW in v3.0)

**File:** `langgraph-agent/app/services/intake_processor.py` — function `build_calendar_hold(parsed: dict) -> str`

The CGCS calendar entry description template is the **authoritative record** of an event's metadata. When the agent creates a HOLD, this 28-field block is rendered into the Google Calendar event's description body. At a glance, any staff member looking at the calendar can discern the event's tier, status, who it's for, what's needed, and what's pending.

**28-Field Template:**

```
Event Name: {event_name}
Status: Pending
Department: {department}
Date of Event: {date}
Time of Event: {start} - {end}
CGCS Lead: TBD
Contact Name / Event Lead: {requestor_name}
Organization / Department: {department_or_org}
Email: {requestor_email}
Phone: {requestor_phone}
Attendance Estimate: {expected_attendance}
Restricted: {External|Internal}
Ad Astra #: Pending
TDX Request #: TBD
Room(s) Reserved: {formatted_room_name}
Floor Layout: {furniture_summary}
Stage Needed: {Yes|No}
Breakdown Time Needed: {breakdown_time}
Additional Needs: {av|catering|linens|alcohol summary}
Walkthrough Date: TBD
Money Expected: {TBD if external, N/A if internal}
Invoice Generated: No
Deposit Paid: No
Payment Method: TBD
Cost Center: CC05070
Spend Category: 5001
Tax Exempt: TBD
Notes: Auto-generated from Smartsheet intake {event_code}
```

**Calendar Title Convention:**

| Prefix | Phase | Example |
|--------|-------|---------|
| `HOLD` | Initial intake | `"HOLD - Spring Community Meeting"` |
| `S-EVENT` | Confirmed internal/service | `"S-EVENT-ACC Faculty Senate"` |
| `C-EVENT` | Confirmed CGCS program | `"C-EVENT-LangChain Meetup"` |
| `A-EVENT` | Confirmed paid revenue event | `"A-EVENT-GAVA Funder Convening"` |

**Promotion workflow:**
1. New Smartsheet intake creates `HOLD - {event_name}` at intake time
2. At Monday team sync, CGCS Lead is assigned (replaces the `TBD` default)
3. When the event is confirmed/invoiced (post-agreement, deposit paid if external), title is manually updated to `S-EVENT-`, `C-EVENT-`, or `A-EVENT-` prefix
4. Remaining fields populate as the workflow progresses (TDX #, walkthrough date, invoice, deposit, etc.)

**Color coding:**
- HOLD: `colorId: 5` (banana yellow)
- Confirmed events: default calendar color (can be updated per tier in future)

### 7.9 P.E.T. Tracker

Unchanged from v2.0 except:
- Spreadsheet ID confirmed: `1GJB70vpHvps50o6inSXbxfufzlY50C-g3KEUp1TEgFE`
- P.E.T. row write from Smartsheet intake is a **pending wiring item** (builders exist; graph node not yet wired into smartsheet_intake flow). Planned for Monday launch punch list.

### 7.10 Event Lead Assignment

Unchanged from v2.0.

### 7.11 Reminders

Unchanged from v2.0 except Gmail API replaces Zoho Mail API for reminder sending.

### 7.12 Revenue Tracking

Unchanged from v2.0.

### 7.13 Compliance Checklist

Unchanged from v2.0.

### 7.14 Dynamic Quote Versioning

Unchanged from v2.0.

### 7.15 Process Insights & AI Recommendations

Unchanged from v2.0.

### 7.16 Daily Digest

Unchanged in mechanics. 8:00 AM CT delivery to `admin@cgcs-acc.org`. Sends 9-section summary.

---
## 8. API Specification

### 8.1 Base URL

- **Local:** `http://localhost:8000`
- **Docker-internal:** `http://langgraph-agent:8000` (from other containers in `cgcs-net`)
- **Production via Coolify edge proxy:** sslip.io subdomain (currently blocked by 504 routing issue — use Docker-internal routing until resolved)

### 8.2 API Version

All endpoints are under `/api/v1/`.

### 8.3 Endpoint Reference (44 total — NEW endpoints marked)

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

#### Smartsheet Intake (NEW in v3.0)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/webhook/smartsheet-new-entry` | Webhook | Push-based trigger (retained but less used; pull-based poller preferred) |
| POST | `/api/v1/smartsheet/poll-now` | API Key | Manually trigger one inbox poll cycle |
| GET | `/api/v1/smartsheet/scheduler-status` | API Key | List scheduler jobs + next run times |

#### Email Triage & Self-Improving Drafts

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/email/triage` | Webhook | Classify email, draft reply, check auto-send |
| POST | `/api/v1/email/approve/{email_id}` | API Key | Approve/reject email draft |
| GET | `/api/v1/email/pending` | API Key | List pending email drafts |
| POST | `/api/v1/email/reject-and-rework/{email_id}` | API Key | Reject draft, generate 3 improved versions |
| POST | `/api/v1/email/select-revision/{pattern_id}` | API Key | Select revision or provide custom draft |
| GET | `/api/v1/email/rejection-insights` | API Key | Rejection analytics and improvement rate |

#### Email Reply Processing (NEW in v3.0)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/webhook/email-reply` | Webhook | Process inbound email reply (classification, edit loop, escalation detection) |

#### Calendar Operations

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/v1/calendar/check` | Webhook | Check Google Calendar availability |
| POST | `/api/v1/calendar/hold` | API Key | Create calendar hold (generic entry point; used by manual flows) |

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

Unchanged from v2.0 (400, 401, 404, 409, 422).

---

## 9. Database Schema

### 9.1 Overview

- **Engine:** PostgreSQL 16
- **Schema:** `cgcs`
- **Driver:** asyncpg with connection pool (min 2, max 10)
- **Tables:** 12
- **Migrations:** 10 files (001–010), applied automatically on container startup

### 9.2 Table Inventory

| Table | Migration | Purpose |
|-------|-----------|---------|
| `reservations` | 001, 005 | Event space reservations with full lifecycle + revenue actuals |
| `audit_trail` | 001 | Activity log for all task types |
| `dead_letter_queue` | 001 | Failed request recovery |
| `pricing_rules` | 001, 002 | Reference: 5 pricing tiers + April 2026 additions |
| `room_configurations` | 001, 002 | Reference: 5 room configs |
| `email_tasks` | 003 | Email triage records |
| `event_leads` | 003 | Staff lead assignments (one per event) |
| `event_reminders` | 003 | Scheduled reminders at 30d/14d/7d/48h |
| `calendar_holds` | 003 | Tentative calendar reservations |
| `pet_staged_updates` | 003 | Staged P.E.T. updates awaiting approval |
| `event_checklist` | 007 | Compliance checklist items with deadlines |
| `email_rejection_patterns` | 008 | Email draft rejection history and revisions |
| `quote_versions` | 009 | Versioned line-item quotes per reservation |
| `smartsheet_intakes` | 010 (NEW) | Smartsheet intake tracking — parsed payload, classification, hold event ID, draft outcomes |

### 9.3 New Table in v3.0

#### cgcs.smartsheet_intakes (Migration 010)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| event_code | VARCHAR(20) | UNIQUE NOT NULL | From Smartsheet (e.g., "1373") |
| gmail_message_id | VARCHAR(100) | | Source Gmail message ID for the notification |
| gmail_thread_id | VARCHAR(100) | | Gmail thread ID (used for draft threading) |
| parsed_payload | JSONB | NOT NULL | Full parsed Smartsheet fields |
| classification | JSONB | | `{difficulty, confidence, reasoning, flags}` |
| hold_event_id | VARCHAR(100) | | Google Calendar event ID for the HOLD |
| hold_html_link | TEXT | | Direct URL to the HOLD on Google Calendar |
| draft_saved | BOOLEAN | DEFAULT FALSE | Whether a Gmail Draft was successfully saved |
| draft_message_id | VARCHAR(100) | | Gmail Draft ID (if saved) |
| is_test_submission | BOOLEAN | DEFAULT FALSE | Flagged test submissions (event name "test"/"testing"/"demo") |
| errors | JSONB | | Array of error strings from graph execution |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | Last modification |

**Indexes:** event_code (UNIQUE), gmail_thread_id, created_at, is_test_submission

### 9.4 Existing Tables

Unchanged from v2.0. See v2.0 specification for full schema of all other tables.

---

## 10. External Service Integrations

### 10.1 Google Calendar API

**File:** `langgraph-agent/app/services/google_calendar.py`
**Authentication:** Service account with Domain-Wide Delegation (impersonates `admin@cgcs-acc.org`)
**Scope:** `https://www.googleapis.com/auth/calendar`
**Timezone:** America/Chicago (CT, UTC-6)
**Calendar ID:** `c_53b8b5f99d7372ea0c513c9fe379461d8fd9c628d883b5b752a95eb5afbe3182@group.calendar.google.com`

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Check availability | GET | `/calendar/v3/calendars/{calendarId}/events` |
| Create hold | POST | `/calendar/v3/calendars/{calendarId}/events` |
| Scan alternative dates | GET (loop) | `/calendar/v3/calendars/{calendarId}/events` |

**Retry:** 3 attempts with exponential backoff (1s, 2s, 4s). HTTP client timeout: 30s.

### 10.2 Google Sheets API

**File:** `langgraph-agent/app/services/google_sheets.py`
**Authentication:** Same service account as Calendar (DWD)
**Scope:** `https://www.googleapis.com/auth/spreadsheets`
**P.E.T. Spreadsheet ID:** `1GJB70vpHvps50o6inSXbxfufzlY50C-g3KEUp1TEgFE`

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Read sheet | GET | `/v4/spreadsheets/{spreadsheetId}/values/{range}` |
| Apply update | PUT | `/v4/spreadsheets/{spreadsheetId}/values/{range}?valueInputOption=USER_ENTERED` |

### 10.3 Gmail API (NEW in v3.0 — replaces Zoho Mail)

**File:** `langgraph-agent/app/services/gmail_service.py` (409 lines)
**Authentication:** Service account with Domain-Wide Delegation (DWD), impersonating `admin@cgcs-acc.org`
**System email:** `admin@cgcs-acc.org` (Google Workspace)

**SCOPES (specific, matching DWD allowlist):**
```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]
```

**Critical fix (commit `8aee105`, 2026-04-20):** Previous SCOPES list contained `["https://mail.google.com/"]` (full-Gmail scope), which was NOT in the Google Workspace Domain-Wide Delegation allowlist. This caused `unauthorized_client` errors on every Gmail API call. Fixed by replacing with the specific four-scope list.

**Public functions:**

| Function | Line | Purpose |
|----------|------|---------|
| `send_email(...)` | 172 | Send an email immediately |
| `read_inbox(query, max_results)` | 202 | Query inbox with Gmail search syntax |
| `get_email(message_id)` | 229 | Fetch full email by message ID |
| `mark_as_read(message_id)` | 247 | Mark message as read |
| `reply_to_thread(...)` | 267 | Send a reply threaded to an existing thread |
| **`create_draft(...)`** | **315** | **NEW in v3.0** — Create a Gmail Draft (not sent) |
| **`create_draft_reply(...)`** | **351** | **NEW in v3.0** — Create a Draft threaded to an existing message |

**Retry:** 3 attempts with exponential backoff. HTTP client timeout: 30s.

**Why draft-first?** In the Smartsheet intake flow, the agent generates a reply but the admin must review before sending. Saving a threaded Draft in Gmail Drafts is the simplest operational handoff — admin opens Gmail, reviews, edits if needed, clicks Send.

### 10.4 Anthropic Claude API

Unchanged in mechanics from v2.0.

**Current model:** `claude-sonnet-4-20250514`
**Note:** Model identifier is configurable via `CLAUDE_MODEL` env var. Upgrade to Sonnet 4.6/4.7 requires only env var change (no code changes).

---

## 11. Authentication & Authorization

Unchanged from v2.0 in mechanics. Material updates:

### 11.1 Network-Level Access Control

**v3.0 change:** Caddy with IP restriction was originally specified for the Caddyfile-based deployment. Now Coolify manages reverse proxy and SSL termination. The IP allowlist pattern is **not currently enforced** — this is a known hardening gap. Recommendation: add nginx / Coolify-level IP restriction before production traffic reaches the agent.

### 11.2 Google Workspace Domain-Wide Delegation (NEW detail)

The service account `cgcs-automation-agent@cgcs-automation.iam.gserviceaccount.com` (client_id `117961396421652014052`) has Domain-Wide Delegation authorized in Google Workspace admin console for these scopes:
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/spreadsheets`
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.compose`
- `https://www.googleapis.com/auth/gmail.send`

**Delegated user:** `admin@cgcs-acc.org`

**Org policy blocker:** The `cgcs-acc.org` Google Cloud organization policy blocks creation of new service account keys. Current key `b1825a6731263b921bff09c126084af9d2138d88` is the only working one. Rotation requires temporarily disabling the org policy, generating the new key, then re-enabling.

---
## 12. Human-in-the-Loop Architecture

### 12.1 Current State (v3.0)

**Material shift from v2.0:** Email ingestion moved from n8n to in-agent APScheduler (ADR-001). n8n retains only trigger-orchestration responsibilities. The primary operational admin surface is **Gmail Drafts** for reviewing and sending replies.

| Interface | Role | What It Does |
|-----------|------|-------------|
| **Gmail Drafts (admin@cgcs-acc.org)** | Primary admin surface | Admin reviews agent-generated drafts, edits if needed, clicks Send. Drafts are already threaded to original Smartsheet notifications. |
| **LangSmith** | LLM observability + review | Traces every LLM call, shows full prompt/response, allows run comparison, flags anomalies |
| **n8n** | Trigger orchestration (reduced scope) | Admin approval webhook (reservations), reminder cron (8am CT daily digest), manual calendar hold triggers |
| **Agent API (direct)** | Structured admin actions | Approve/reject reservations, reject-and-rework emails, checklist updates, quote generation |
| **CGCS Command Dashboard** | Planned unified admin UI | Not yet built. Next.js + React, API key auth against FastAPI backend. |

### 12.2 ADR-001: Email Monitoring Lives in the Agent

**Decision:** Move email ingestion from n8n cron-polling to an in-agent APScheduler job.

**Context:** Previously, n8n polled Zoho Mail every 5 minutes, called `POST /api/v1/email/triage` for each unread email. This coupled email flow to n8n's availability and log rotation, and spread debugging across two systems.

**Alternatives considered:**
- Keep n8n as the poller (status quo): rejected because it meant debugging two systems when drafts were wrong
- Event-driven push via Google Workspace Pub/Sub: rejected for now because DWD + Pub/Sub setup is non-trivial and adds a GCP dependency

**Chosen:** APScheduler in the FastAPI lifespan. The agent is self-contained — it polls Gmail on its own schedule, classifies, drafts, saves to Gmail Drafts. n8n remains for webhook-triggered work but is no longer load-bearing for the inbox flow.

**Consequences:**
- ✅ Simpler operational model (one process, one log stream)
- ✅ Poller restarts atomically with agent
- ✅ Gmail Drafts become the HITL surface (no separate admin queue)
- ⚠️ Agent restart briefly pauses polling (acceptable — 5 min cycles; a missed cycle just means next cycle processes 10 instead of 5)
- ⚠️ Scaling horizontally would require a distributed lock to prevent duplicate processing (not needed at current volume)

### 12.3 CGCS Command Dashboard (Still Planned)

Purpose-built admin dashboard for unified operational view. Same plan as v2.0 §12.4.

---

## 13. Business Rules & Constants

**File:** `langgraph-agent/app/cgcs_constants.py`

### 13.1 Hours of Operation

Unchanged from v2.0:

| Day | Building Hours | Event Hours |
|-----|---------------|-------------|
| Monday-Thursday | 7:00 AM - 10:00 PM | 8:00 AM - 9:00 PM |
| Friday | 7:00 AM - 5:00 PM | 8:00 AM - 4:30 PM |
| Weekend | Conditional | Requires police ($65/hr, 4hr min) + police agreement + CGCS support staff |

### 13.2 Pricing Tiers — April 2026 Revision

Legacy tiers (from v2.0):

| Tier | Hourly Rate | Minimum Hours | Description |
|------|-------------|---------------|-------------|
| acc_internal | $0.00 | 1 | ACC departments, programs, faculty, staff |
| government_agency | $0.00 | 1 | Federal, state, local government agencies |
| nonprofit | $25.00 | 2 | Nonprofit organizations with civic/government missions |
| community_partner | $50.00 | 2 | Community partners with educational missions |
| external | $100.00 | 3 | External organizations |

### 13.3 AMI Facility Pricing — April 2026 Revision

**Main Hall (RGC3.3340, capacity 350):**

| Block | Price |
|-------|-------|
| Half-Day (morning OR afternoon) | $625 |
| Full Day | $1,200 |
| Extended | $1,500 |
| Weekend Hourly | $200/hr (+$65/hr police, 4hr min) |

**Meeting Rooms (new tier structure):**

| Room Type | Half-Day | Full-Day |
|-----------|---------:|---------:|
| CGCS Classroom (RGC3.3328, capacity 24) | $200 | $375 |
| Small Conference (capacity 15) | $150 | $275 |
| Flexible Meeting Space | Contact for quote | Contact for quote |

### 13.4 Add-On Services — April 2026 Revision

| Service | Rate | Unit | Notes |
|---------|------|------|-------|
| **AV Basic** | **$160** | **flat** | **Simple hybrid/Zoom setup (changed from per-hour in v2.0)** |
| AV Technician | $160 | flat | ACC technician assignment (via TDX) |
| Webcast / Large Hybrid Add-On | $100 | additional flat | |
| Round Tables | $15 | each | Includes linens + ACC moving team |
| External Furniture Movement | $250 | coordination fee | For furniture not part of CGCS inventory |
| Stage Setup | $150 | flat | |
| Stage Teardown | $100 | flat | |
| Admin Support | Up to $250 | flat | |
| Signage | $100 | flat | Creation + wayfinding |
| Catering Coordination | $100 | surcharge | If CGCS coordinates with ACC Catering |
| Police Coverage | $65 | per hour (4-hour minimum) | Required for weekends, >50 attendees, Fri evenings |
| Cleanup Fee (if space not reset) | $300 | flat | Applied to both Internal and External users |

### 13.5 Tiered Discounts (NEW in v3.0)

Applied as percentage off the AMI Facility Pricing base:

| Discount | Percentage | Eligibility |
|----------|-----------:|-------------|
| Nonprofit (civic/government mission) | 25% | Verified 501(c)(3) status |
| Government Agency | 40% | Federal, state, local government |
| Recurring Client | 10% | 3+ bookings in prior 12 months |

Discounts stack additively (e.g., government + recurring = 50%), capped at 50% total. Decided at admin discretion during quote approval.

### 13.6 Labor Rates

Unchanged from v2.0.

| Role | Staff | Hourly Rate |
|------|-------|-------------|
| Director / Event Lead | Bryan Port | $66.00 |
| Intern Event Lead | Brenden Fogg, Catherine Thomason, Eimanie Thomas, Marisela Perez Maita, Stefano Casafranca Laos, Tzur Shalit, Vanessa Trujano | $25.00 |
| Intake Processing | Austin Wells | $25.00 |

### 13.7 Deadlines (Business Days Before Event)

**Aligned between Internal and External user agreements (see §22):**

| Deadline | Business Days | Notes |
|----------|---------------|-------|
| CGCS Response | 3 | Agreement commitment |
| TDX AV Request | 15 | Complex AV (simple AV handled in-house) |
| Walkthrough | 12 | Required for all events |
| Run of Show / Diagram | 10 | Earlier if possible |
| Furniture Setup | 10 | Same as run of show |
| ACC Catering | 25 | For ACC Catering service |
| Special Services (security/signage) | 20 | For External users |

### 13.8 Financial

- **A-EVENT Deposit Rate:** 5% (External requests)
- **Internal Deposit:** None
- **Cost Center:** CC05070
- **Spend Category:** 5001
- **Cleanup Fee:** $300 (if space not reset)

### 13.9 COI (Certificate of Insurance) Requirement — EXTERNAL

For all external events, COI is required with CGCS listed as additional insured:
- **Certificate Holder:** Austin Community College District
- **Attn:** Risk Management Dept.
- **Address:** 6101 Highland Campus Drive, Austin, TX 78752

### 13.10 Room Configurations

Unchanged from v2.0 in the abstract config. Physical rooms confirmed:

| Room | Code | Capacity |
|------|------|---------:|
| CGCS Main Hall | RGC3.3340 | 350 |
| CGCS Classroom | RGC3.3328 | 24 |
| Meeting Room RGC3.3346 | RGC3.3346 | 3 |
| Meeting Room RGC3.3347 | RGC3.3347 | 4 |
| Conference Room RGC3.3348 | RGC3.3348 | 10 |
| Lecture Room | RGC3.3325 | 24 |

### 13.11 Event Type Classification

| Prefix | Description |
|--------|-------------|
| HOLD- | Pending intake (initial state for all new events) |
| S-EVENT- | Service/partner/internal (no revenue) |
| C-EVENT- | CGCS programs (simulations, hackathons, LangChain meetup, design jams) |
| A-EVENT- | Paid/AMI (revenue-generating) |

### 13.12 VIP & Auto-Send Rules

Unchanged from v2.0:

**VIP Senders:**
- `michelle.raymond@austincc.edu` (ACC Strategic Planning)
- Subject mentions "Office of the Chancellor"

**Auto-Send Allowlist:**
- `stefano.casafrancalaos@austincc.edu`
- `marisela.perez@austincc.edu`

**Current state:** Smartsheet intake flow **never** auto-sends; always saves to Gmail Drafts. Auto-send for allowlisted senders is a post-launch roadmap item.

### 13.13 Escalation Routing

For emails flagged as escalations (legal language, supervisor requests, complaints):

**Forward-to list:**
- `michelle.raymond@austincc.edu`
- `admin@cgcs-acc.org`
- `austin.wells@austincc.edu`

### 13.14 28-Field Calendar Entry Template

See §7.8 for the full template. Rendered by `build_calendar_hold(parsed)` in `intake_processor.py`.

### 13.15 P.E.T. Tracker Columns (20)

| # | Column | Source |
|--:|--------|--------|
| 1 | Event Name | Smartsheet |
| 2 | Status | System (Pending/Confirmed/Completed/Cancelled) |
| 3 | Entered into Calendar | System (Yes/No + calendar event link) |
| 4 | CGCS/AMI/STEWARDSHIP | Admin assignment at Monday sync |
| 5 | Date of event | Smartsheet |
| 6 | Time of event | Smartsheet |
| 7 | CGCS Lead | Monday sync assignment |
| 8 | Contact Information/Event Lead | Smartsheet |
| 9 | Attendance | Smartsheet |
| 10 | Money Expected | External: from quote. Internal: N/A |
| 11 | Ad Astra Number # | From Smartsheet (Event Code field) |
| 12 | TDX Request # | Filed by admin post-intake (if A/V needed) |
| 13 | Floor Layout | Smartsheet (furniture summary) |
| 14 | Stage? | Derived from furniture items |
| 15 | Breakdown Time Needed | Smartsheet |
| 16 | Additional Needs | Smartsheet (AV/linens/catering/alcohol) |
| 17 | Walkthrough Date | Scheduled during admin review |
| 18 | Invoice Generated | System flag |
| 19 | Rooms | Smartsheet (formatted display name) |
| 20 | CGCS Labor | Monday sync notes |

### 13.16 Acknowledgment Email Template

Updated signature for v3.0:

```
Dear {first_name},

Thank you for submitting your event space reservation request to the Center for Government & Civic Service at Austin Community College.

We have received your request and it is now being reviewed. You can expect a response within 3 business days.

If you have any questions in the meantime, please don't hesitate to reach out.

Best regards,
CGCS Team
admin@cgcs-acc.org
www.cgcsacc.org
```

### 13.17 Event Checklist Template

Unchanged from v2.0. 10 items auto-generated on intake approval.

---

## 14. Prompt Engineering

**File:** `langgraph-agent/app/prompts/templates.py`

### 14.1 Prompt Inventory (14 total — NEW marked)

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
| **Smartsheet Easy Response Template** | Parameterized | `_draft_easy_response` (deterministic, not LLM) | NEW — short confirmation for easy classifications |
| **Smartsheet Review Response Template** | Parameterized | `_draft_review_response` (deterministic, not LLM) | NEW — detailed response for mid/hard, surfaces flags |
| **Furniture Coordination Template** | Parameterized | `draft_furniture_email` | NEW — email to Tyler/Scott |
| **Police Coordination Template** | Parameterized | `draft_police_email` | NEW — email to James Ortiz |
| **Internal vs External Branching Rules** | Inline | Draft templates | NEW — different tone/content per requester type |
| **Rejection Lessons Injection** | Dynamic | `get_rejection_lessons()` | NEW — format for feeding prior corrections into future drafts |

### 14.2 Self-Improving Prompts

Unchanged from v2.0 in mechanics.

### 14.3 Email Drafting Rules (v3.0 Updated)

- Never CC Bryan Port on any emails (flag high-profile to Bryan separately)
- Sign as "CGCS Team" with `admin@cgcs-acc.org` + `www.cgcsacc.org` (NOT Austin's personal name/email)
- Attach User Agreement (Internal or External based on `is_external`) + Parking Map to initial response (implementation pending — see §23)
- Reference the 3 business day response commitment
- Mention requested room name (e.g., "CGCS Main Hall (RGC3.3340)") when known
- For spam, return empty string (no reply drafted)
- For complaints, acknowledge concerns and offer to connect with appropriate staff
- Don't claim "calendar hold placed" unless `state["hold_event_id"]` is present

### 14.4 Voice Corpus (Post-Launch Plan)

Post-launch weeks 2-3 roadmap item. Austin provides 5-8 of his best real outbound CGCS emails (e.g., the Caroline financial aid department training email from Apr 20). Corpus feeds the LLM drafting prompt as few-shot examples. Template remains as fallback.

Gold-standard example captured for corpus:

**From:** Austin Wells
**To:** Caroline (financial aid department)
**Date:** 2026-04-20
**Topic:** June 5 training event
**Key moves:** Warm personal opener; confident availability confirmation; specific form direction; AV decision tree (simple = in-house, complex = TDX); catering optionality; room number education (3340 main, 3328 classroom); concrete pricing ($15/table gala rounds); walkthrough offer; clear call-to-action.

---

## 15. Error Handling & Resilience

Unchanged from v2.0 in mechanics. Material additions:

### 15.1 Smartsheet Intake continueOnFail Matrix (NEW)

| Operation | Failure Behavior |
|-----------|-----------------|
| Calendar HOLD creation | Logged; draft still generated; error appended to `state["errors"]` but flow continues |
| P.E.T. row write (when wired) | Logged; draft still generated |
| Gmail Draft save | Logged; intake record still created in DB; admin can manually draft |
| Gmail mark_as_read | Logged; email may reprocess on next cycle (idempotent via `event_code` unique constraint) |

### 15.2 Poller Idempotency

The `smartsheet_intakes.event_code UNIQUE` constraint prevents duplicate processing if the poller reprocesses an email before `mark_as_read` succeeded. The second attempt returns early with a log entry ("already processed event_code=X").

---

## 16. Security Architecture

Unchanged from v2.0 in primary mechanics. Material updates:

### 16.1 Secret Management

All secrets managed via Coolify's environment variable UI (backed by Docker secrets). Also replicated to Proton Pass (CGCS vault, 17 items) for team continuity:

| Secret | Location | Notes |
|--------|----------|-------|
| `ANTHROPIC_API_KEY` | Coolify + Proton Pass | Rotated 2026-04-18. Old key still needs deletion from Anthropic console. |
| `LANGGRAPH_API_KEY` | Coolify + Proton Pass | Used for admin endpoints |
| `WEBHOOK_SECRET` | Coolify + Proton Pass | Current value hex-encoded 64-char |
| `POSTGRES_PASSWORD` | Coolify + Proton Pass | Database access |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Coolify as file secret | DWD service account |
| `LANGCHAIN_API_KEY` | Coolify + Proton Pass | LangSmith |
| `ZOHO_MAIL_TOKEN` | Proton Pass (DEPRECATED — can be deleted) | Zoho retired |
| `GITHUB_CLI_TOKEN` | Proton Pass | For gh CLI |
| `HETZNER_API_TOKEN` | Proton Pass | For VPS management |

### 16.2 Authentication Hardening (TODO)

- Re-enable IP allowlist at Coolify / reverse proxy layer (currently disabled after move from Caddy)
- Rotate webhook secret after launch
- Rotate GitHub CLI tokens

---
## 17. Deployment & Infrastructure

### 17.1 Hetzner VPS (NEW in v3.0)

**Specs:**

| Field | Value |
|-------|-------|
| Provider | Hetzner Cloud |
| Instance Type | CPX22 |
| vCPU | 3 (shared) |
| RAM | 4 GB |
| Storage | 80 GB NVMe SSD |
| OS | Ubuntu 24.04 LTS |
| Public IP | 46.225.111.82 |
| Location | US (Ashburn) |
| Cost | ~$8–10/month |

### 17.2 Coolify PaaS

**Version:** v4
**Purpose:** Self-hosted deployment platform that handles Docker orchestration, GitHub integration, SSL certificates, logs, and environment variable management.

**Admin UI:** `http://46.225.111.82:8000`

**Deploy flow:**
1. `git push origin main` in `~/Desktop/ai-intake/`
2. GitHub App fires webhook to Coolify
3. Coolify pulls latest code
4. Coolify builds Docker image from `langgraph-agent/Dockerfile`
5. Coolify rolling-restarts the `langgraph-agent` service
6. Healthcheck passes → new version live

**Typical deploy time:** 2-3 minutes.

### 17.3 Docker Compose Services (4)

| Service | Image | Internal Port | Healthcheck |
|---------|-------|---------------|-------------|
| **coolify-proxy** | Coolify-managed | 80, 443 | - |
| **n8n** | `n8nio/n8n:latest` | 5678 | - |
| **langgraph-agent** | Custom build from repo | 8000 | `curl -f /api/v1/health` every 30s |
| **postgres** | `postgres:16-alpine` | 5432 | `pg_isready` every 10s |

All services on shared Docker network `cgcs-net`. Container-to-container calls work by service name (e.g., `http://langgraph-agent:8000`).

### 17.4 Database Initialization

Migrations applied automatically on PostgreSQL container first start. Current migration file count: 10.

### 17.5 Known Infrastructure Issues

**Coolify edge proxy 504 on external routing:**
- Symptom: External calls to the agent's sslip.io URL return 504 Gateway Timeout
- Internal container-to-container routing works fine
- Workaround: Pull-based poller + internal n8n webhook calls (all work without external routing)
- Blocker for: External integrations that need to call agent directly
- Not a launch blocker since the poller is fully internal

---

## 18. Observability & Monitoring

### 18.1 LangSmith Integration

Unchanged from v2.0. Project: `cgcs-automation`.

### 18.2 Logging

Unchanged from v2.0. Key v3.0 log events added:

```
"Smartsheet poll cycle start (job_id=...)"
"Processed Smartsheet intake event_code=1373"
"Calendar HOLD created: event_id=abc123"
"Calendar HOLD creation failed (continueOnFail): {error}"
"Gmail Draft saved: draft_id=..., thread_id=..."
"Scheduler job scheduled: next_run={iso_ts}"
```

### 18.3 Audit Trail

New actor types in v3.0:

| Actor | New Actions |
|-------|-------------|
| `smartsheet_poller` | `intake_polled`, `intake_processed`, `intake_skipped_duplicate` |
| `langgraph_agent` | `calendar_hold_created_from_intake`, `furniture_email_drafted`, `police_email_drafted` |

---

## 19. Testing & Evaluation

### 19.1 Test Suite

- **Framework:** pytest + pytest-asyncio + pytest-mock
- **Test count:** 604 passing tests, 0 failures
- **Test files:** 17 (was 13 in v2.0)

| File | New in v3.0? | Coverage Focus |
|------|:------------:|---------------|
| test_api.py | - | Endpoint routing, auth, validation |
| test_graph.py | - | Node execution, state transitions |
| test_email_triage.py | - | Ad Astra, VIP, auto-send, calendar invite |
| test_calendar.py | - | Availability, hold creation |
| test_leads.py | - | Staff roster, monthly cap |
| test_acknowledgment.py | - | Template rendering |
| test_checklist.py | - | Compliance checklist |
| test_reports.py | - | Revenue, conversion funnel, CSV |
| test_rejection.py | - | Rejection storage, rework |
| test_quotes.py | - | Quote versioning |
| test_process_insights.py | - | Analytics, recommendations |
| test_labor_rates.py | - | Labor rate constants |
| **test_smartsheet_parser.py** | ✅ | Parser field extraction (subject + body) |
| **test_smartsheet_intake.py** | ✅ | classify_request, draft templates, furniture/police emails |
| **test_smartsheet_poller.py** | ✅ | Poll cycle, Gmail query, threading, mark_as_read |
| **test_scheduler.py** | ✅ | APScheduler lifecycle, job registration |
| **test_email_reply.py** | ✅ | Reply classifier, edit loop counter, escalation detection |
| conftest.py | - | Shared test fixtures |

### 19.2 Running Tests

```bash
PYTHONPATH=langgraph-agent \
  ANTHROPIC_API_KEY=test-key \
  DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test \
  python -m pytest tests/ -v
```

### 19.3 End-to-End Validation (2026-04-21)

Real Smartsheet form submission validated the full pipeline:
- Event: "test", Date 04/26/26 (Sunday), Internal, austinwells8225@gmail.com
- Flow: Smartsheet → `austin.wells@austincc.edu` → Gmail filter auto-forward → `admin@cgcs-acc.org` → poller → graph → Gmail Draft threaded to original
- Result: `{"status":"ok","checked":1,"processed":1,"skipped":0,"errors":[]}`
- Draft quality post `e204242`: professional, honest, surfaces weekend-police coordination flag correctly

---

## 20. Configuration Reference

### 20.1 Environment Variables

**New in v3.0:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMARTSHEET_POLL_ENABLED` | No | `true` | Master toggle for inbox poller |
| `SMARTSHEET_POLL_MINUTES` | No | `5` | Poll cycle interval |
| `SMARTSHEET_POLL_MAX_EMAILS` | No | `10` | Max emails processed per cycle |
| `GMAIL_DELEGATED_USER` | Yes | `admin@cgcs-acc.org` | User impersonated via DWD |

**Deprecated in v3.0 (remove from env):**
- `ZOHO_MAIL_TOKEN` — Zoho retired
- `ZOHO_ACCOUNT_ID` — Zoho retired

All other v2.0 env vars retained.

---

## 21. Data Flow Diagrams

### 21.1 Smartsheet Intake Flow (NEW in v3.0)

```
Smartsheet form submission
      |
      v
Smartsheet notification email -> austin.wells@austincc.edu
      |
      v (Gmail filter auto-forward)
admin@cgcs-acc.org inbox
      |
      v (every 5 min: APScheduler -> smartsheet_inbox_poller)
Gmail query: "is:unread from:@app.smartsheet.com subject:'Notice of Event Space Request'"
      |
      v (for each matching email)
parse_smartsheet_intake(subject, body) -> parsed dict
      |
      v
Graph invocation: task_type=smartsheet_intake, smartsheet_parsed={...}
      |
      v
classify_intake_request -> classification = {difficulty, flags}
      |
      v
create_hold_from_intake:
  build_calendar_hold(parsed) -> 28-field description
  build_calendar_title("HOLD", event_name) -> "HOLD - {name}"
  google_calendar.create_hold(...) -> event_id, html_link
  -> state: hold_event_id, hold_html_link
  (continueOnFail: error logged but does not abort)
      |
      v
draft_intake_emails:
  draft_intake_response(parsed, classification) -> main reply
  draft_furniture_email(parsed) -> coordination email to Tyler/Scott (if needed)
  draft_police_email(parsed) -> coordination email to James Ortiz (if needed)
      |
      v
For each draft: gmail_service.create_draft_reply(thread_id, to, subject, body)
      |
      v
gmail_service.mark_as_read(original_message_id)
      |
      v
INSERT INTO cgcs.smartsheet_intakes (event_code, hold_event_id, draft_saved, ...)
      |
      v
Admin opens Gmail Drafts at admin@cgcs-acc.org
      |
      v
Admin reviews, edits if needed, clicks Send
```

### 21.2 Event Intake Flow

Unchanged from v2.0. Gmail API replaces Zoho Mail API for outbound sending.

### 21.3 Email Triage Flow

Unchanged from v2.0 in logic. Changes:
- Gmail API instead of Zoho
- Poller is in-agent (not n8n cron)

### 21.4 Daily Digest Flow

Unchanged from v2.0. Delivered to `admin@cgcs-acc.org` at 8:00 AM CT via n8n cron → agent → Gmail.

### 21.5 Quarterly Report Flow

Unchanged from v2.0.

---

## 22. User Agreements

Both agreements revised and finalized 2026-04-22. Distributed with initial intake response email (attachment wiring pending — see §23).

### 22.1 External User Agreement

16 sections, finalized. Key updates from prior version:
- All submission contacts consolidated to `austin.wells@austincc.edu` + `admin@cgcs-acc.org`
- $300 cleanup fee standardized
- 90-day cancellation terms preserved
- Liability & Compliance section (Section 16) retained

**Distributed as:** `CGCS-EXTERNAL-User_Agreement-UPDATED.docx` (includes parking map + floor layouts)

### 22.2 Internal User Agreement

15 sections, finalized 2026-04-22. Major structural changes from prior version:
1. **Removed:** `teamcgcs@gmail.com` references (consolidated to `admin@cgcs-acc.org`)
2. **Removed:** Annamelly Ortiz references (not in CGCS processes)
3. **Removed:** Zannie Garvin from user-facing content (CGCS handles internally)
4. **Reorganized:** Revenue-Driven Rescheduling + Calendar Hold Limitations moved to top as Section 1 ("Reservation Terms")
5. **Added:** Reservation Workflow at top (Ad Astra → Smartsheet form → CGCS response → signed agreement)
6. **Added:** Cancellation section with 10-business-day cost-absorption threshold
7. **Added:** Liability & Compliance section
8. **Added:** $300 cleanup fee (matching External)
9. **Aligned:** AV lead time (15 business days), catering (25 business days), run of show (10 business days)
10. **Signature:** POC is Austin Wells, contact `admin@cgcs-acc.org`

**Distributed as:** `CGCS-INTERNAL-User-Agreement-REVISED-branded.docx` (with CGCS + ACC logos in header, Garamond body font)

### 22.3 Distribution Convention

Agreement PDF attached to initial reply email based on `is_external` flag in parsed Smartsheet data. Parking Map PDF always attached. Wiring to pass attachments via `create_draft_reply(attachments=[...])` is a pending punch list item.

---

## 23. Launch Status & Punch List

**Launch Target:** Monday 2026-04-27

**As of 2026-04-22 PM, the following is the operational state:**

### 23.1 Production-Validated

- ✅ Hetzner VPS live, Coolify v4 running
- ✅ PostgreSQL 16 with 10 migrations applied
- ✅ FastAPI agent running, all 44 endpoints responding to internal calls
- ✅ n8n running with Event Space Intake workflow active
- ✅ Gmail API operational with DWD (after scope fix `8aee105`)
- ✅ Google Calendar API operational
- ✅ Google Sheets API operational
- ✅ Smartsheet inbox poller running every 5 minutes
- ✅ APScheduler lifespan integration working
- ✅ 604 tests passing, 0 failures
- ✅ Real end-to-end Smartsheet → Gmail Draft validated
- ✅ Draft template quality improved (commit `e204242`)
- ✅ Both user agreements finalized

### 23.2 Punch List — Before Launch (2026-04-27)

| # | Item | Priority | Estimated Effort |
|--:|------|----------|------------------|
| 1 | Wire calendar HOLD creation into smartsheet_intake flow | P0 | In progress |
| 2 | Wire P.E.T. row write node | P0 | 1-2 hrs (builders exist, just needs node + edge) |
| 3 | Attachment support in `create_draft_reply` (Internal/External Agreement + Parking Map) | P0 | 2-3 hrs |
| 4 | Test-submission filter (event name "test"/"testing"/"demo" → `[TEST]` prefix, no attachments) | P1 | 30 min |
| 5 | Publish admin-approval n8n workflow | P1 | 1 hr |
| 6 | Publish reminder-cron n8n workflow (8am CT digest) | P1 | 1 hr |
| 7 | Debug Coolify edge proxy 504 (external routing) | P2 | Time-boxed 2 hrs; not launch-blocking |
| 8 | Commit ADR-001 to `~/Desktop/ai-intake/docs/` | P2 | 10 min |

### 23.3 Post-Launch (Weeks 2-3)

| # | Item | Owner |
|--:|------|-------|
| 1 | LLM drafting layer (voice corpus from 5-8 Austin emails, system prompt, fallback to template) | Austin |
| 2 | Self-improvement loop wiring (`rejection_queries.py` + `process_insights.py` feedback loop) | Austin |
| 3 | Delete old Anthropic API key from console (pre-rotation key still active) | Austin |
| 4 | Rotate GitHub CLI tokens | Austin |
| 5 | Rotate webhook secret | Austin |
| 6 | Update Google Workspace billing before 2026-05-01 | Austin |
| 7 | Pitch Brian/Michelle to add `admin@cgcs-acc.org` to Smartsheet recipients directly | Austin |
| 8 | Replace sslip.io with proper domain + HTTPS | Austin |
| 9 | Post-graduation handoff documentation | Austin |

### 23.4 Deferred (v3.1+)

| # | Item | Notes |
|--:|------|-------|
| 1 | CGCS Command Dashboard (Next.js/React) | Consolidates admin actions into one UI |
| 2 | Active email-to-calendar updates (agent modifies calendar entry description on reply) | Bigger scope: needs calendar entry lookup by thread_id |
| 3 | Tier auto-assignment at intake time | Currently all intakes start as HOLD; tier decided at Monday sync |
| 4 | Composable agent split (intake agent, email agent, calendar agent, reports agent) | v4.0 roadmap |

---

## 24. Roadmap — v4.0 Architecture

### 24.1 Composable Agent Architecture

**Current (v3.0):** Monolithic — one FastAPI app, one AgentState, one state machine handling all 14 capabilities.

**Target (v4.0):** Composable — smaller specialized agents communicating through a message bus or orchestrator.

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
- Each agent has its own focused state (not 110+ fields)
- Independent deployment and scaling
- Failure isolation (email agent crash doesn't affect intake)
- Easier testing (test each agent in isolation)

### 24.2 LLM Output Evaluation Framework

Automated evals on every LLM call:

| Eval | Check | Action |
|------|-------|--------|
| Email contains requester name | Regex check | Flag if missing |
| Email mentions date | Regex for YYYY-MM-DD or month name | Flag if missing |
| Email under word limit | Word count < 500 | Flag if exceeded |
| Eligibility matches known cases | Compare against curated test dataset | Alert on divergence |
| Pricing tier matches org type | Rule-based check | Alert on mismatch |
| Recommendations are specific | Check for concrete numbers/percentages | Flag if generic |
| Draft cites hold_event_id when present | State-vs-output consistency | Flag if draft claims hold without ID |

### 24.3 Guardrails Layer

Schema validation and content filtering on all LLM responses:
- **Schema validation**: Pydantic models for every LLM output
- **Content filtering**: No pricing before admin review, no unauthorized commitments
- **Hallucination detection**: Verify LLM-generated facts match input data (dates, names, amounts)

### 24.4 CGCS Command Dashboard

Purpose-built admin dashboard (Next.js + React + Recharts). Same plan as v2.0/v3.0.

### 24.5 LLM Drafting with Voice Corpus

Post-launch weeks 2-3 (see §23.3). Moves from deterministic templates to Claude-generated drafts with Austin's voice as few-shot examples.

### 24.6 Self-Improvement Loop Activation

Full wire-up of existing `rejection_queries.py` + `process_insights.py`:
- Capture every admin edit
- Diff original draft vs sent version
- Feed diffs back into future prompts
- Quarterly review of improvement metrics

### 24.7 Confidence-Based Auto-Send

Today, only two email addresses are on the auto-send allowlist. Post voice-corpus LLM drafting:
- High parser confidence + high classifier confidence + matching safe patterns → auto-send
- Allowlist grows via earned trust, not hardcoded adds

### 24.8 Productization as White-Label SaaS

Exploratory: package the architecture as a SaaS offering for nonprofits, civic orgs, and higher-ed facility management. Evaluate post-launch (Q3 2026+).

---

## Appendices

### A. Glossary

| Term | Definition |
|------|------------|
| CGCS | Center for Government & Civic Service at Austin Community College |
| AMI | Austin Meeting & Innovation (facility pricing model for paid events) |
| P.E.T. | Program Event Tracker (Google Sheets-based operational tracker) |
| DLQ | Dead Letter Queue (failed request recovery system) |
| DWD | Domain-Wide Delegation (Google Workspace service account impersonation) |
| n8n | Open-source workflow automation platform (trigger/orchestration layer) |
| TDX | TeamDynamix (ACC's AV/IT request system) |
| AAIS | Ad Astra Information Systems (ACC room scheduling platform) |
| ACC | Austin Community College |
| RGC | Rio Grande Campus (1218 West Ave, Building 3000) |
| CT | Central Time (America/Chicago) |
| HITL | Human-in-the-Loop |
| continueOnFail | Error handling pattern where failure is logged but doesn't block main flow |
| ADR | Architecture Decision Record |
| Coolify | Self-hosted PaaS (like Heroku) used for deployment on Hetzner |

### B. Contact Information

| Role | Name | Email |
|------|------|-------|
| CGCS Admin | Austin Wells | austin.wells@austincc.edu |
| CGCS System Email | - | admin@cgcs-acc.org (Google Workspace) |
| Director / Supervisor | Bryan Port | bryan.port@austincc.edu |
| Strategic Planner (colleague) | Marisela Perez Maita | marisela.perez@austincc.edu |
| Intake / Email Lead | Brenden Fogg | brenden.fogg@g.austincc.edu |
| VIP (Strategic Planning) | Michelle Raymond | michelle.raymond@austincc.edu |
| Moving Team | Tyler Briery, Scott Farmer | tyler.briery@austincc.edu, scott.farmer@austincc.edu |
| Police Coordination | James Ortiz | james.ortiz@austincc.edu |

### C. Infrastructure References

| Resource | Value |
|----------|-------|
| Hetzner VPS | 46.225.111.82 (CPX22, Ubuntu 24.04) |
| Coolify UI | `http://46.225.111.82:8000` |
| Live n8n webhook | `http://h26cllcwo5xtb6yaszqjdxkv.46.225.111.82.sslip.io/webhook/intake/event-space` |
| GitHub repo | `austinwells8225-sys/cgcs-automation` |
| Google Calendar ID | `c_53b8b5f99d7372ea0c513c9fe379461d8fd9c628d883b5b752a95eb5afbe3182@group.calendar.google.com` |
| P.E.T. Sheet ID | `1GJB70vpHvps50o6inSXbxfufzlY50C-g3KEUp1TEgFE` |
| Service account | `cgcs-automation-agent@cgcs-automation.iam.gserviceaccount.com` |
| Service account client_id | `117961396421652014052` |

### D. External URLs

| Resource | URL |
|----------|-----|
| CGCS Website | https://www.cgcsacc.org |
| Smartsheet Intake Form | https://app.smartsheet.com/b/form/cd2f5559c5b6458fbfe61490f4a90f93 |
| TDX AV Portal | https://acchelp.austincc.edu/TDClient/277/Portal/Requests/ServiceDet?ID=10656 |
| Ad Astra | https://www.aaiscloud.com/AustinCC/ |

### E. Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0 | 2026-03-02 | Initial technical specification (8 capabilities, 19 endpoints, 96 tests) |
| 2.0 | 2026-03-03 | Added 6 capability modules, labor rates, LangSmith HITL, composable roadmap, Zoho → Google migration plan (12 capabilities, 38 endpoints, 228 tests) |
| 3.0 | 2026-04-22 | Production deployment on Hetzner/Coolify; Zoho retired; Gmail API live with DWD; Smartsheet inbox poller + APScheduler in-agent (ADR-001); Smartsheet intake capability; Email Reply processing; 28-field calendar entry template; revised user agreements (Internal + External); April 2026 pricing revision; Gmail Drafts as primary HITL surface (14 capabilities, 44 endpoints, 604 tests) |

---

*This document is the authoritative technical reference for the CGCS Unified Agent system as of 2026-04-22. For operational procedures and user guides, see the README.md. For v2.0, see TECHNICAL_SPECIFICATION_v2_0.md. For v1.0, see TECHNICAL_SPECIFICATION_v1_0.md.*
