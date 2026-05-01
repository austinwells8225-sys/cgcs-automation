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
- Event lead assignment + reminder scheduling (30d/14d/7d/48h)
- Daily digest (11 sections)
- Compliance checklist with deadlines
- Versioned line-item quotes
- Reports: revenue, conversion funnel, top orgs, compliance, process insights
- Dashboard alerts (AV/catering changes, dead-letter)

## Commands
- Start: `docker compose up -d`
- Tests: `PYTHONPATH=langgraph-agent python -m pytest tests/ -v`
- Health: `curl http://localhost:8000/api/v1/health`

## Prompts Up to date with Output

The CGCS AI intake system is built and operating in human-in-the-loop draft-only mode: an APScheduler job polls admin@cgcs-acc.org every five minutes for unread emails matching `from:@app.smartsheet.com subject:"Notice of Event Space Request"`, runs each through the LangGraph smartsheet_intake subgraph which parses 40+ fields, classifies the request as easy/mid/hard with reasoning and flags, creates a Google Calendar HOLD with a 30+ field description, appends a row to the P.E.T. tracker spreadsheet, and produces a Gmail draft reply (plus furniture coordination email to the Moving Team and after-hours police email to Officer Ortiz when those flags trigger) — the inbox poller never calls send so every outbound reply waits in Gmail Drafts for Austin's approval; the calendar HOLD and P.E.T. row are written before draft approval so rejecting a draft currently leaves both behind for manual cleanup; deployment targets Coolify on a self-hosted VPS with the agent listening on port 8000 behind Coolify's HTTPS proxy, and the docker-compose.yml now exports GMAIL_DELEGATED_USER, SMARTSHEET_POLL_ENABLED, and SMARTSHEET_POLL_MINUTES alongside the existing Google API and Anthropic vars; the immediate path to live is (1) set real values in the Coolify .env for ANTHROPIC_API_KEY, LANGGRAPH_API_KEY, WEBHOOK_SECRET, GOOGLE_CALENDAR_ID, PET_TRACKER_SPREADSHEET_ID, and GMAIL_DELEGATED_USER, (2) confirm the service-account JSON is mounted and Google Workspace domain-wide delegation is enabled for Gmail/Calendar/Sheets scopes, (3) smoke-test with one real Smartsheet email and verify draft + hold + sheet row appear, (4) review 3-5 real drafts before tuning prompts; the planned next phase is a Next.js dashboard at ops.cgcs-acc.org (api.cgcs-acc.org for the agent) with Google OAuth restricted to @austincc.edu and a group login for the CGCS team, rendering pages for inbox approval (highest priority), revenue, active reservations, and alerts on top of the existing /reports/*, /email/pending, /alerts/active, and /dead-letter endpoints — CGCS controls cgcs-acc.org DNS so DNS is not blocked.
