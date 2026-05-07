---
title: CGCS Unified Agent — Project State
generated: 2026-05-06
project_root: /Users/a2068129/Desktop/ai-intake
authoritative_spec: TECHNICAL_SPECIFICATION_v3_0.md
status: live in production, post-launch iteration
audience: LLMs and engineers picking up the project cold
---

# CGCS Unified Agent — Project State

> **Read me first.** This is a snapshot of what the project *is*, *where it is*, and *where it's going*, written so an LLM with no prior context can be productive in one read. For deeper detail see `TECHNICAL_SPECIFICATION_v3_0.md`. For commit-by-commit history see `git log`.

---

## 0. TL;DR

- **What it is:** An AI agent + ops dashboard that automates event-space intake, eligibility evaluation, pricing, calendar holds, email triage/replies, reminders, and impact reporting for the **Center for Government & Civic Service (CGCS)** at Austin Community College.
- **Posture:** **Human-in-the-loop.** No outbound email is sent without admin approval (review happens in Gmail). Drafts are pre-attached, threaded, and ready to send.
- **Where it is now (2026-05-06):** Live on a Hetzner VPS via Coolify. 14 AI-powered capabilities behind a single unified LangGraph state machine, 46 FastAPI endpoints, 12 Postgres tables, 604 passing tests. Latest feature: auto-attach the correct internal/external user-agreement PDF on first-reachout drafts.
- **Where it's going:** (1) Unblock final go-live items (Smartsheet form re-route, DNS, prod env vars). (2) Replace deterministic email templates with LLM drafting trained on Austin's voice corpus. (3) Activate the self-improvement loop (admin edits → future prompt few-shots). (4) Confidence-gated auto-send for allowlisted senders. (5) v4.0: split monolithic agent into 5 specialized agents + add evals + guardrails.

---

## 1. Glossary (acronyms used everywhere)

| Term | Meaning |
|------|---------|
| **CGCS** | Center for Government & Civic Service — ACC unit that runs the event venue at Rio Grande Campus, Building 3000 |
| **ACC** | Austin Community College |
| **P.E.T.** | Operational Google Sheet ("People / Events / Tasks") tracker that the CGCS team uses day-to-day |
| **HITL** | Human-in-the-loop |
| **DWD** | Domain-Wide Delegation (Google Workspace service-account impersonation) |
| **DLQ** | Dead Letter Queue (failed-graph-execution recovery table) |
| **HOLD** | Tentative calendar reservation created during intake, before final confirmation |
| **First-reachout** | Initial inbound cold email from an external requester (not a reply in an existing thread) |
| **Easy / Mid / Hard** | LLM intake classification tiers driving how much human review is required |

---

## 2. Goal & Vision

### 2.1 Problem
CGCS administrator (Austin Wells) was the manual workflow for every event request: read Smartsheet form, check calendar, evaluate eligibility, calculate pricing, draft a reply, attach the right agreement, create a calendar hold, log the row in P.E.T., schedule reminders, follow up, generate reports. This does not scale and is error-prone.

### 2.2 Solution
A unified AI agent that performs all of the above as a state machine, **drafts** outbound communications, and surfaces them for admin approval in Gmail itself — so the admin's review surface is the inbox they already live in. A Next.js dashboard supplements with metrics, alerts, and inbox/reservation views.

### 2.3 North Star
- **Never send an unauthorized email.** Drafts only, except for a small allowlist of internal staff.
- **Never lose a request.** Failed runs go to a Dead Letter Queue with full state.
- **Improve over time.** Capture every admin edit; use it to retrain prompts.
- **Surface impact.** Roll up every event into the four-tier impact view (Community → Monetization → ACC → CGCS) with YoY deltas.

### 2.4 Stakeholders
| Person | Role |
|--------|------|
| Austin Wells | CGCS admin / primary user / project owner |
| Bryan Port | Director — owns the four-tier impact narrative |
| Michelle Raymond | ACC IT contact (owns the Smartsheet form re-route blocker) |
| Marisela Perez | Internal staff — on auto-send allowlist (planned) |
| Stefano Casafranca-Laos | Internal staff — on auto-send allowlist (planned) |

---

## 3. Architecture (one screen)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          External World                                  │
│  Smartsheet form  ──▶  Gmail (admin@cgcs-acc.org)  ◀──  External email  │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │  (every 5 min, APScheduler poll)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  langgraph-agent  (FastAPI + LangGraph + Claude Sonnet 4)               │
│  ─────────────────────────────────────────────────────────────────────  │
│  router → { event_intake | smartsheet_intake | email_triage |           │
│             email_reply  | calendar_check    | calendar_hold |          │
│             pet_tracker  | event_lead        | reminder_check |         │
│             daily_digest } → END                                        │
│  ─────────────────────────────────────────────────────────────────────  │
│  Side effects:  Gmail drafts │ Calendar HOLDs │ P.E.T. row appends │    │
│                 Postgres writes │ DLQ on failure                        │
└────────────┬──────────────────────┬─────────────────────────────────────┘
             │                      │
             ▼                      ▼
   ┌────────────────────┐   ┌──────────────────────────┐
   │   Postgres 16      │   │   cgcs-dashboard         │
   │   (12 tables,      │◀──│   (Next.js 15 + NextAuth │
   │    011 migrations) │   │    Google OAuth)         │
   └────────────────────┘   └──────────────────────────┘

   ┌──────────────┐
   │     n8n      │  legacy / fallback orchestrator (mostly retired)
   └──────────────┘
```

**Key invariant:** the state machine is **one** AgentState TypedDict (~110 fields) routed by `task_type`. Non-critical operations (auto-quote, stats writes) never block the main flow; failures get caught and logged, not raised.

---

## 4. Components

### 4.1 `langgraph-agent/` — the core (Python)
| Concern | Stack |
|---|---|
| LLM | Claude Sonnet 4 via `langchain-anthropic` |
| Graph | `langgraph` 0.3 StateGraph |
| API | FastAPI 0.115 + Uvicorn (**single worker** so APScheduler runs once) |
| DB | Postgres 16 + `asyncpg` |
| Scheduler | APScheduler 3.10 (lives inside FastAPI lifespan) |
| Google APIs | Gmail, Calendar, Sheets via service account + DWD |
| Tracing | LangSmith (optional, on in prod) |

**Module map (`langgraph-agent/app/`):**
- `main.py` (~68 KB) — FastAPI app, all 46 endpoints, lifespan hooks, request/response models. Refactor candidate, not urgent.
- `graph/builder.py` — wires nodes + edges into the unified graph.
- `graph/state.py` — `AgentState` TypedDict, ~110 fields.
- `graph/nodes/` — 15 node files (router, intake, calendar, email_triage, email_reply, smartsheet_intake, calendar_hold, pet_tracker, event_lead, reminders, daily_digest, shared).
- `graph/edges.py` — `after_routing`, `after_eligibility`, `after_intake_classification`, etc.
- `services/` — 14 modules. Notables:
  - `gmail_service.py` — read / draft / threaded reply / attach / mark-read
  - `google_calendar.py` — availability + 28-field HOLD descriptions
  - `google_sheets.py` — P.E.T. tracker read/append
  - `intake_classifier.py` — Easy / Mid / Hard via LLM
  - `intake_processor.py` — deterministic templates for acks + intake drafts
  - `reply_processor.py` — edit-loop tracking, escalation detection, furniture/AV change detection
  - `smartsheet_parser.py` — extracts 40+ fields from Smartsheet notification emails
  - `smartsheet_inbox_poller.py` — APScheduler Gmail poller (every 5 min) → triggers graph
  - `agreement_attacher.py` — picks Internal vs External agreement PDF by sender domain ⭐ newest
  - `quote_builder.py` — line-item quotes (AV Basic, room tiers, labor, nonprofit discounts)
  - `process_insights.py` — monthly stats, quarterly reports, AI recommendations
- `db/` — 10 async query modules; **no SQL in main.py**.
- `prompts/templates.py` — 14 LLM system prompts.
- `cgcs_constants.py` — pricing tiers, labor rates, room configs, eligibility rules, email templates. Edit business logic here, not in code.
- `models.py` — 50+ Pydantic models.
- `migrations_runner.py` — applies any unapplied SQL on startup; idempotent. Added 2026-05-05 because long-lived DBs were missing migrations added after first launch.

**Graph (state machine):**
```
START → route_task → {
  event_intake     : validate → eligibility → pricing → room_setup → draft_intake_emails → END
  smartsheet_intake: validate → classify(Easy/Mid/Hard) → create_hold → write_pet_row → draft_intake_emails → END
  email_triage     : classify_email → draft_reply → check_auto_send → END
  email_reply      : process_reply(edit-loop +1, detect escalation) → draft_reply → END
  calendar_check   : check_availability → END
  calendar_hold    : validate_hold → create_hold → END
  pet_tracker      : read → prepare_update → END
  event_lead       : assign_lead → schedule_reminders(30d/14d/7d/48h) → END
  reminder_check   : find_due → send → END
  daily_digest     : build_digest(11 sections) → END
}
```

### 4.2 `cgcs-dashboard/` — Next.js ops UI
| Concern | Stack |
|---|---|
| Framework | Next.js 15.1.8, React 18.3.1, TypeScript 5.7 |
| Styling | Tailwind 3.4 |
| Auth | NextAuth 4.24 + Google OAuth, restricted to `@austincc.edu` / `@cgcs-acc.org` |
| Charts | Recharts 2.15 |

| Route | Purpose | Status |
|---|---|---|
| `/` | Four-tier impact homepage with YoY | **LIVE** |
| `/inbox` | Pending email drafts; one-click approve/reject | **FUNCTIONAL** |
| `/alerts` | AV/catering changes, DLQ errors | **READY** |
| `/events/manual` | Manually log off-site CGCS events | **FUNCTIONAL** |
| `/reservations` | Reservation table | **STUB** (data ready, UI not built) |
| `/surveys` | Post-event survey ingestion | **STUB** (Google Form webhook planned) |

### 4.3 `db/` — Postgres schema
- 11 migration files (`001` … `011_impact_metrics`).
- 12 tables in the `cgcs` schema: `reservations`, `audit_trail`, `dead_letter_queue`, `email_tasks`, `event_leads`, `event_reminders`, `calendar_holds`, `pet_staged_updates`, `event_checklist`, `email_rejection_patterns`, `quote_versions`, `dashboard_alerts` (+ `canonical_events`, `canonical_event_aliases`, `event_surveys` from migration 011).
- Migration runner is in the agent (`migrations_runner.py`); applies unapplied migrations idempotently on startup.

### 4.4 `n8n/` — legacy
Still present, mostly superseded. Workflows kept for manual triggers and as a fallback orchestrator. Most polling/cron logic now lives in the agent.

### 4.5 `tests/` — pytest
604 tests passing, 0 failing, 6,829 LOC across 21 files. Strong coverage of: smartsheet parsing (568 LOC), process insights (791 LOC), intake processor + classifier, quote versioning, reply processor edit loops, checklist, date utils, rejection patterns, agreement attacher, graph routing.

```bash
PYTHONPATH=langgraph-agent python -m pytest tests/ -v
```

### 4.6 `docker-compose.yml` — service wiring
4 services: `postgres` (16-alpine, mounts `db/migrations/*` into init dir), `langgraph-agent` (build from `./langgraph-agent`, port 8000), `cgcs-dashboard` (build from `./cgcs-dashboard`, port 3000), `n8n` (port 5678). Each tagged with Coolify labels for auto-proxy.

### 4.7 `.env.example` — external integrations
| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude Sonnet 4 |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Service account JSON for DWD |
| `GMAIL_DELEGATED_USER` | `admin@cgcs-acc.org` (system mailbox impersonated) |
| `GOOGLE_CALENDAR_ID` | CGCS Events calendar |
| `PET_TRACKER_SPREADSHEET_ID` | P.E.T. operational sheet |
| `LANGCHAIN_API_KEY` | LangSmith tracing (optional) |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | Dashboard auth |
| `NEXTAUTH_SECRET` | NextAuth session secret |
| `WEBHOOK_SECRET` | Shared secret for n8n ↔ agent |
| `SMARTSHEET_POLL_ENABLED`, `SMARTSHEET_POLL_MINUTES` | Inbox poll cadence |

---

## 5. Current State (2026-05-06)

### 5.1 Production
- **Host:** Hetzner CPX22, Ubuntu 24.04, 4 vCPU / 16 GB RAM, IP `46.225.111.82`.
- **Deploy:** Coolify v4 with GitHub App auto-deploy from `austinwells8225-sys/cgcs-automation`.
- **DNS (planned):** `api.cgcs-acc.org`, `ops.cgcs-acc.org` → Coolify VPS.
- **Observability:** LangSmith on for HITL tracing.

### 5.2 Recent commits (momentum signal)
```
18f6709  feat: auto-attach the right CGCS user-agreement PDF on first-reachout drafts   (May 6)
686cfc4  feat(agent): startup migration runner so new SQL applies to long-lived DBs     (May 5)
9f124da  fix(dashboard): add public/ dir so Docker COPY doesn't choke                   (May 4)
4660fd6  fix(dashboard): pin React 18 + patched Next, move authOptions to lib           (May 3)
3ca84c5  feat(impact+dashboard): four-tier impact rollup + Next.js ops dashboard        (May 1)
a187e1d  chore(infra): expose Gmail + Smartsheet poller env vars in compose             (Apr 23)
81803d3  fix(infra): single Uvicorn worker so APScheduler runs once, not twice          (Apr 23)
```
Read: project is in **post-launch iteration mode** — production fixes, dashboard launch, legal-compliance polish.

### 5.3 What's working today
- Smartsheet email intake → classification → calendar HOLD → P.E.T. row → drafted reply.
- Email triage on the admin inbox; reply drafts threaded to original.
- Calendar availability checks + 28-field HOLD descriptions.
- Reminder scheduling at 30d / 14d / 7d / 48h tiers.
- Daily digest with 11 sections.
- Quote versioning with line-item line items + nonprofit discounts.
- Auto-attach correct agreement PDF on first-reachout drafts.
- Four-tier impact homepage with YoY deltas.
- Dashboard inbox approve/reject server actions.
- Manual off-site event entry form.
- Compliance checklist storage.
- Email-rejection-pattern capture (the ground floor of the self-improvement loop).
- Migration runner self-heals long-lived DBs on startup.

### 5.4 What is *not* yet wired
- **Self-improvement loop activation:** rejection patterns are *captured* but not yet *fed back* into drafting prompts as few-shots.
- **Auto-send for allowlist:** allowlist exists in code; UI/approval gates not wired.
- **LLM-drafted email body:** today's drafts come from deterministic templates in `cgcs_constants.py`. Voice corpus + LLM drafting is post-launch.
- **Reservations dashboard page:** stub only; data is in DB.
- **Survey ingestion:** `event_surveys` table exists; Google Form webhook not wired.
- **Canonical-event de-dup matcher:** tables exist; matching algorithm not trained (needs more live data).

### 5.5 Code-quality observations
- No `TODO` / `FIXME` markers in agent code. Codebase is clean.
- `main.py` is large (68 KB / all 46 endpoints inline). Modularization is a refactor candidate, not urgent.
- Clear separation: nodes / services / db queries / prompts / constants. Easy to navigate cold.

---

## 6. Where It's Going

### 6.1 Immediate (blocking go-live, this week)
1. **Smartsheet form re-route** — Michelle Raymond updates the Smartsheet form destination to a new ACC Google Group `cgcs-group@austincc.edu`. Today's workaround: `austin.wells@austincc.edu` receives forwarded notifications via a Gmail filter. Zero code change once it lands; the poller adapts.
2. **Coolify env vars** — set real values for `ANTHROPIC_API_KEY`, `WEBHOOK_SECRET`, `GOOGLE_CALENDAR_ID`, `PET_TRACKER_SPREADSHEET_ID`, `NEXTAUTH_SECRET`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`.
3. **Confirm Workspace DWD scopes** for `cgcs-acc.org`.
4. **Point DNS** for `api.cgcs-acc.org` and `ops.cgcs-acc.org`.
5. **Smoke-test:** one real Smartsheet intake, one cold first-reachout email (verify agreement is auto-attached), render Impact page live.

### 6.2 Post-launch (weeks 2–8) — from `TECHNICAL_SPECIFICATION_v3_0.md` §24
| Priority | Item | Notes |
|---|---|---|
| 1 | **LLM drafting w/ voice corpus** | Replace deterministic templates. Austin provides 5–8 real email examples; few-shot in prompts. |
| 2 | **Activate self-improvement loop** | Wire `rejection_queries.py` + `process_insights.py` into draft prompt; capture admin edits; diff original-vs-sent and fold back as few-shots. |
| 3 | **Confidence-based auto-send** | Allowlist + high parser/classifier confidence + matching safe pattern → auto-send. Requires (1) and (2) first. |
| 4 | **Reservations table UI** | Build out `/reservations` with filtering and detail/edit views. |
| 5 | **Survey ingestion** | Google Form webhook → `event_surveys` → impact metrics. |
| 6 | **Canonical event de-dup matcher** | Train on live data; validate "River Hacks = Space Apps = NASA Space Apps" patterns. |

### 6.3 v4.0 (architectural) — from `TECHNICAL_SPECIFICATION_v3_0.md` §24
- **Composable agents:** split the unified state machine into 5 specialized agents (Intake, Email, Calendar, Reports, Compliance) communicating over a message bus.
- **Eval framework:** automated checks on every LLM call (name, date, word limit, eligibility match, pricing tier match, recommendation specificity, `hold_event_id` consistency — 7 in total).
- **Guardrails layer:** schema validation + content filtering on all LLM responses (no pricing before approval, no unauthorized commitments, hallucination detection).

### 6.4 Exploratory (Q3 2026+)
Productize as a white-label SaaS for nonprofits, civic orgs, and higher-ed facility management. Not committed; evaluate post-launch.

---

## 7. Design Decisions Worth Knowing

| Decision | Why |
|---|---|
| **Single unified state machine, not microservices** | Simpler ops; one AgentState carries everything; routing does the rest. v4.0 may split. |
| **Gmail drafts as the approval surface** | Admin lives in inbox already; no custom approval UI needed. Threaded replies preserve context. |
| **Single Uvicorn worker** | APScheduler must run exactly once. Multi-worker → duplicate polls. (See commit `81803d3`.) |
| **Email ingestion in agent, not n8n (ADR-001)** | Fewer failure surfaces; APScheduler in FastAPI lifespan is enough. |
| **Deterministic + LLM hybrid** | LLM never owns critical business logic (pricing, eligibility). LLM is for personalization/tone. Voice-corpus drafting is post-launch. |
| **Agreement attacher is rule-based, not LLM** | Sender domain decides Internal vs External. Cheap, deterministic, auditable, legal-safe. |
| **Migration runner inside the app** | Long-lived prod DBs were missing migrations added after first deploy. Runner self-heals on startup; idempotent. |
| **Rejection patterns stored in DB** | Capture *now*, retrain *later*. Ground floor of the self-improvement loop. |

---

## 8. File Map (cheat sheet)

```
ai-intake/
├── README.md                              high-level overview (13 KB)
├── TECHNICAL_SPECIFICATION_v3_0.md        authoritative spec (90 KB, 25 sections)
├── BUILD_SCRIPT.md / BUILD_SCRIPT_FULL.md document-as-system rolling summary
├── CLAUDE.md                              Claude Code build-script rules
├── docker-compose.yml                     4 services
├── .env.example                           required env vars
│
├── langgraph-agent/
│   └── app/
│       ├── main.py                        FastAPI + 46 endpoints (refactor candidate)
│       ├── graph/
│       │   ├── builder.py                 graph wiring
│       │   ├── state.py                   AgentState TypedDict
│       │   ├── edges.py                   routing decisions
│       │   └── nodes/                     15 node files
│       ├── services/                      14 modules (Gmail, Calendar, Sheets, classifier, parser, attacher, quote, insights, poller, scheduler …)
│       ├── db/                            10 async query modules
│       ├── prompts/templates.py           14 LLM prompts
│       ├── cgcs_constants.py              pricing/rates/rooms/eligibility/templates
│       ├── models.py                      50+ Pydantic models
│       ├── config.py                      .env loader
│       └── migrations_runner.py           startup migration self-heal
│
├── cgcs-dashboard/
│   └── app/                               page.tsx (impact), inbox/, alerts/, events/, reservations/, surveys/
│
├── db/migrations/                         001 … 011_impact_metrics
├── n8n/                                   legacy workflow JSON
├── caddy/                                 unused (Coolify proxies instead)
├── credentials/                           gitignored Google service-account JSON
└── tests/                                 21 files, 604 tests, 6,829 LOC
```

---

## 9. How to be productive in this repo (LLM checklist)

1. **Goal/spec questions** → `README.md`, then `TECHNICAL_SPECIFICATION_v3_0.md` (§ matters: §24 = roadmap).
2. **What changed recently** → `git log --oneline -30`.
3. **Business rules** (pricing, rooms, eligibility, templates) → `langgraph-agent/app/cgcs_constants.py`.
4. **Adding a capability** → new node in `graph/nodes/`, wire in `graph/builder.py`, add `task_type` route in `route_task` + `edges.py`, extend `AgentState` if needed, add tests.
5. **Adding an endpoint** → `main.py` (be aware: it's already 68 KB — modularize if you add a lot).
6. **Schema change** → new `db/migrations/0NN_*.sql`. The runner will pick it up on next deploy. Add `db/queries/...` or extend an existing query module.
7. **LLM prompt change** → `langgraph-agent/app/prompts/templates.py`.
8. **Run the test suite** → `PYTHONPATH=langgraph-agent python -m pytest tests/ -v`.
9. **Don't break HITL.** Outbound email goes to Gmail Drafts only, except the explicit allowlist. If a change could send unsupervised email, gate it behind confidence + allowlist + opt-in flag.
10. **Don't add SQL to `main.py`.** Query modules in `db/` are the contract.
