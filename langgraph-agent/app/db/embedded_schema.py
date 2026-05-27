# AUTO-GENERATED. Regenerate by concatenating db/migrations/*.sql.
# Used as a fallback bootstrap when the migrations directory bind-mount
# fails (e.g., some Coolify Compose deploys).

EMBEDDED_SQL = r"""-- CGCS Event Space Automation Engine
-- Initial schema: reservations, audit trail, pricing, room configurations

SET search_path TO cgcs, public;

-- Enums
CREATE TYPE cgcs.reservation_status AS ENUM (
    'pending_review',
    'approved',
    'rejected',
    'cancelled',
    'completed'
);

CREATE TYPE cgcs.pricing_tier AS ENUM (
    'acc_internal',
    'government_agency',
    'nonprofit',
    'community_partner',
    'external'
);

CREATE TYPE cgcs.room_type AS ENUM (
    'large_conference',
    'small_conference',
    'event_hall',
    'classroom',
    'multipurpose'
);

-- Reservations table
CREATE TABLE cgcs.reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(64) UNIQUE NOT NULL,
    requester_name VARCHAR(255) NOT NULL,
    requester_email VARCHAR(255) NOT NULL,
    requester_organization VARCHAR(255),
    event_name VARCHAR(500) NOT NULL,
    event_description TEXT,
    requested_date DATE NOT NULL,
    requested_start_time TIME NOT NULL,
    requested_end_time TIME NOT NULL,
    room_requested cgcs.room_type,
    estimated_attendees INTEGER,
    setup_requirements JSONB,
    pricing_tier cgcs.pricing_tier,
    estimated_cost DECIMAL(10,2),
    is_eligible BOOLEAN,
    eligibility_reason TEXT,
    calendar_available BOOLEAN,
    ai_decision VARCHAR(20), -- 'approve', 'reject', 'needs_review'
    ai_draft_response TEXT,
    status cgcs.reservation_status DEFAULT 'pending_review',
    admin_approved_at TIMESTAMPTZ,
    admin_notes TEXT,
    response_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit trail table
CREATE TABLE cgcs.audit_trail (
    id BIGSERIAL PRIMARY KEY,
    reservation_id UUID REFERENCES cgcs.reservations(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pricing rules table
CREATE TABLE cgcs.pricing_rules (
    id SERIAL PRIMARY KEY,
    tier cgcs.pricing_tier UNIQUE NOT NULL,
    hourly_rate DECIMAL(10,2) NOT NULL,
    minimum_hours INTEGER DEFAULT 1,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Room configurations table
CREATE TABLE cgcs.room_configurations (
    id SERIAL PRIMARY KEY,
    room cgcs.room_type UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    max_capacity INTEGER NOT NULL,
    available_equipment JSONB,
    setup_options JSONB,
    google_calendar_id VARCHAR(255) NOT NULL
);

-- Dead letter queue for failed processing
CREATE TABLE cgcs.dead_letter_queue (
    id BIGSERIAL PRIMARY KEY,
    request_id VARCHAR(64),
    payload JSONB NOT NULL,
    error_message TEXT NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    failure_count INTEGER DEFAULT 1,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'resolved', 'expired'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100)
);

-- Indexes
CREATE INDEX idx_reservations_status ON cgcs.reservations(status);
CREATE INDEX idx_reservations_date ON cgcs.reservations(requested_date);
CREATE INDEX idx_reservations_email ON cgcs.reservations(requester_email);
CREATE INDEX idx_audit_trail_reservation ON cgcs.audit_trail(reservation_id);
CREATE INDEX idx_audit_trail_created ON cgcs.audit_trail(created_at);
CREATE INDEX idx_dead_letter_status ON cgcs.dead_letter_queue(status);
CREATE INDEX idx_dead_letter_request ON cgcs.dead_letter_queue(request_id);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION cgcs.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER reservations_updated_at
    BEFORE UPDATE ON cgcs.reservations
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();
-- CGCS Unified Agent — Multi-capability expansion
-- New tables: email_tasks, event_leads, event_reminders, calendar_holds, pet_staged_updates
-- ALTER audit_trail: nullable reservation_id, add task_type + task_id

SET search_path TO cgcs, public;

-- ============================================================
-- Email triage records
-- ============================================================
CREATE TABLE cgcs.email_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(64) UNIQUE NOT NULL,
    email_id VARCHAR(255),
    email_from VARCHAR(255) NOT NULL,
    email_to VARCHAR(255),
    email_subject TEXT,
    email_body TEXT,
    priority VARCHAR(20) DEFAULT 'medium',        -- high, medium, low
    category VARCHAR(50) DEFAULT 'other',          -- event_request, question, complaint, follow_up, spam, other
    draft_reply TEXT,
    auto_send BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'pending_review',   -- pending_review, approved, rejected, sent
    admin_notes TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_email_tasks_status ON cgcs.email_tasks(status);
CREATE INDEX idx_email_tasks_priority ON cgcs.email_tasks(priority);
CREATE INDEX idx_email_tasks_from ON cgcs.email_tasks(email_from);

CREATE TRIGGER email_tasks_updated_at
    BEFORE UPDATE ON cgcs.email_tasks
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();

-- ============================================================
-- Event lead assignments
-- ============================================================
CREATE TABLE cgcs.event_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID REFERENCES cgcs.reservations(id) ON DELETE CASCADE,
    request_id VARCHAR(64),
    staff_name VARCHAR(255) NOT NULL,
    staff_email VARCHAR(255) NOT NULL,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(reservation_id)
);

CREATE INDEX idx_event_leads_staff ON cgcs.event_leads(staff_email);
CREATE INDEX idx_event_leads_reservation ON cgcs.event_leads(reservation_id);

CREATE TRIGGER event_leads_updated_at
    BEFORE UPDATE ON cgcs.event_leads
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();

-- ============================================================
-- Event reminders (30d/14d/7d/48h)
-- ============================================================
CREATE TABLE cgcs.event_reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID REFERENCES cgcs.reservations(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES cgcs.event_leads(id) ON DELETE CASCADE,
    staff_email VARCHAR(255) NOT NULL,
    reminder_type VARCHAR(20) NOT NULL,            -- 30_day, 14_day, 7_day, 48_hour
    remind_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',           -- pending, sent, skipped, failed
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reminders_status_date ON cgcs.event_reminders(status, remind_date);
CREATE INDEX idx_reminders_reservation ON cgcs.event_reminders(reservation_id);

CREATE TRIGGER event_reminders_updated_at
    BEFORE UPDATE ON cgcs.event_reminders
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();

-- ============================================================
-- Calendar holds
-- ============================================================
CREATE TABLE cgcs.calendar_holds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(64),
    org_name VARCHAR(255) NOT NULL,
    hold_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    google_event_id VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active',            -- active, released, converted
    created_by VARCHAR(100) DEFAULT 'admin',
    released_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_holds_date ON cgcs.calendar_holds(hold_date);
CREATE INDEX idx_holds_status ON cgcs.calendar_holds(status);

CREATE TRIGGER calendar_holds_updated_at
    BEFORE UPDATE ON cgcs.calendar_holds
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();

-- ============================================================
-- P.E.T. staged updates
-- ============================================================
CREATE TABLE cgcs.pet_staged_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    staged_id VARCHAR(64) UNIQUE NOT NULL,
    row_data JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',           -- pending, approved, rejected, applied
    approved_by VARCHAR(100),
    approved_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pet_staged_status ON cgcs.pet_staged_updates(status);

CREATE TRIGGER pet_staged_updated_at
    BEFORE UPDATE ON cgcs.pet_staged_updates
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();

-- ============================================================
-- ALTER audit_trail for multi-capability support
-- ============================================================
-- reservation_id is already nullable, just add new columns
ALTER TABLE cgcs.audit_trail
    ADD COLUMN IF NOT EXISTS task_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS task_id VARCHAR(64);

CREATE INDEX idx_audit_trail_task ON cgcs.audit_trail(task_type, task_id);
-- CGCS Event Space Automation Engine
-- Revenue and attendance tracking columns on reservations

SET search_path TO cgcs, public;

-- Add revenue/attendance tracking columns to reservations
ALTER TABLE cgcs.reservations
    ADD COLUMN IF NOT EXISTS actual_revenue DECIMAL(10,2),
    ADD COLUMN IF NOT EXISTS actual_attendance INTEGER,
    ADD COLUMN IF NOT EXISTS event_department VARCHAR(255),
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;

-- Indexes for reporting queries
CREATE INDEX IF NOT EXISTS idx_reservations_completed_at ON cgcs.reservations(completed_at);
CREATE INDEX IF NOT EXISTS idx_reservations_cancelled_at ON cgcs.reservations(cancelled_at);
CREATE INDEX IF NOT EXISTS idx_reservations_event_department ON cgcs.reservations(event_department);
-- CGCS Event Space Automation Engine
-- Compliance checklist for approved events

SET search_path TO cgcs, public;

CREATE TABLE cgcs.event_checklist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL REFERENCES cgcs.reservations(id) ON DELETE CASCADE,
    item_key VARCHAR(50) NOT NULL,
    item_label VARCHAR(255) NOT NULL,
    required BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, in_review, completed, waived
    deadline_date DATE,
    completed_at TIMESTAMPTZ,
    completed_by VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(reservation_id, item_key)
);

CREATE INDEX idx_checklist_reservation ON cgcs.event_checklist(reservation_id);
CREATE INDEX idx_checklist_status_deadline ON cgcs.event_checklist(status, deadline_date);

CREATE TRIGGER event_checklist_updated_at
    BEFORE UPDATE ON cgcs.event_checklist
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();
-- 008_rejection_patterns.sql
-- Tracks email draft rejections and AI-generated revisions for self-improving prompts.

CREATE TABLE IF NOT EXISTS cgcs.email_rejection_patterns (
    id              SERIAL PRIMARY KEY,
    email_task_id   UUID REFERENCES cgcs.email_tasks(id),
    original_draft  TEXT NOT NULL,
    rejection_reason TEXT NOT NULL,
    revision_options JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_revision_index INT,
    final_draft     TEXT,
    category        VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Reuse the shared updated_at trigger function
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON cgcs.email_rejection_patterns
    FOR EACH ROW
    EXECUTE FUNCTION cgcs.update_updated_at();

CREATE INDEX idx_rejection_patterns_category
    ON cgcs.email_rejection_patterns(category);

CREATE INDEX idx_rejection_patterns_created
    ON cgcs.email_rejection_patterns(created_at DESC);

CREATE INDEX idx_rejection_patterns_email_task
    ON cgcs.email_rejection_patterns(email_task_id);
-- 009_quote_versions.sql
-- Dynamic quote versioning: tracks pricing changes as event requirements evolve.

CREATE TABLE IF NOT EXISTS cgcs.quote_versions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id        UUID NOT NULL REFERENCES cgcs.reservations(id) ON DELETE CASCADE,
    version               INTEGER NOT NULL DEFAULT 1,
    line_items            JSONB NOT NULL,
    subtotal              DECIMAL(10,2) NOT NULL,
    deposit_amount        DECIMAL(10,2) DEFAULT 0,
    total                 DECIMAL(10,2) NOT NULL,
    changes_from_previous JSONB,
    notes                 TEXT,
    created_by            VARCHAR(100) DEFAULT 'admin',
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(reservation_id, version)
);

CREATE INDEX idx_quote_versions_reservation
    ON cgcs.quote_versions(reservation_id);

CREATE INDEX idx_quote_versions_latest
    ON cgcs.quote_versions(reservation_id, version DESC);
-- Dashboard alerts for AV/catering changes and other notifications
CREATE TABLE IF NOT EXISTS cgcs.dashboard_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID,
    alert_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    detail TEXT,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON cgcs.dashboard_alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON cgcs.dashboard_alerts (alert_type);
-- CGCS Event Space Automation Engine
-- Migration 011: Impact metrics (Bryan's storytelling tiers)
-- Adds event categorization, attendance disaggregation, off-site CGCS event
-- support, canonical event identity (de-dup), and post-event surveys.

SET search_path TO cgcs, public;

-- --- Enums ----------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE cgcs.event_category AS ENUM ('monetization', 'acc', 'cgcs');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE cgcs.event_subtype AS ENUM ('training', 'convening', 'co_branded', 'other');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE cgcs.event_location AS ENUM ('on_site', 'off_site');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- --- Reservations: categorization + disaggregation ------------------------

ALTER TABLE cgcs.reservations
    ADD COLUMN IF NOT EXISTS event_category cgcs.event_category,
    ADD COLUMN IF NOT EXISTS event_subtype cgcs.event_subtype,
    ADD COLUMN IF NOT EXISTS event_location cgcs.event_location DEFAULT 'on_site',
    ADD COLUMN IF NOT EXISTS attendance_students INTEGER,
    ADD COLUMN IF NOT EXISTS attendance_staff INTEGER,
    ADD COLUMN IF NOT EXISTS attendance_community INTEGER,
    ADD COLUMN IF NOT EXISTS training_hours_delivered DECIMAL(6,2),
    ADD COLUMN IF NOT EXISTS canonical_event_id UUID,
    ADD COLUMN IF NOT EXISTS source VARCHAR(32) DEFAULT 'smartsheet';

-- Best-effort retroactive classification of existing rows.
-- Anything that doesn't match falls through to 'monetization' so revenue is
-- still counted; admins can re-classify in the dashboard.
UPDATE cgcs.reservations
SET event_category = 'cgcs'::cgcs.event_category
WHERE event_category IS NULL
  AND (
    event_name ILIKE '%cgcs%' OR
    event_name ILIKE '%austin forum%' OR
    event_name ILIKE '%ai alliance%' OR
    event_name ILIKE '%langchain%' OR
    event_name ILIKE '%lang chain%' OR
    event_name ILIKE '%acm%' OR
    event_name ILIKE '%hackathon%' OR
    event_name ILIKE '%simulation%' OR
    requester_organization ILIKE '%cgcs%'
  );

UPDATE cgcs.reservations
SET event_category = 'acc'::cgcs.event_category
WHERE event_category IS NULL
  AND (
    requester_email ILIKE '%@austincc.edu' OR
    requester_organization ILIKE '%austin community college%' OR
    requester_organization ILIKE '%acc %' OR
    requester_organization ILIKE 'acc'
  );

UPDATE cgcs.reservations
SET event_category = 'monetization'::cgcs.event_category
WHERE event_category IS NULL;

-- --- Canonical event identity (de-dup across systems) ---------------------

CREATE TABLE IF NOT EXISTS cgcs.canonical_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(500) NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cgcs.canonical_event_aliases (
    id BIGSERIAL PRIMARY KEY,
    canonical_event_id UUID NOT NULL REFERENCES cgcs.canonical_events(id) ON DELETE CASCADE,
    alias VARCHAR(500) NOT NULL,
    source VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (canonical_event_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_canonical_event_aliases_alias
    ON cgcs.canonical_event_aliases(LOWER(alias));

-- --- Off-site / manual-entry CGCS events ----------------------------------
-- Lives in the same reservations table as on-site events so all rollups
-- pick it up automatically. source='manual' lets us tell them apart.

-- --- Post-event surveys ---------------------------------------------------

CREATE TABLE IF NOT EXISTS cgcs.event_surveys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID REFERENCES cgcs.reservations(id) ON DELETE CASCADE,
    canonical_event_id UUID REFERENCES cgcs.canonical_events(id) ON DELETE SET NULL,
    respondent_role VARCHAR(64),
    would_attend_again BOOLEAN,
    would_recommend BOOLEAN,
    confidence_increased BOOLEAN,
    skills_applicable BOOLEAN,
    free_text TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_surveys_reservation ON cgcs.event_surveys(reservation_id);
CREATE INDEX IF NOT EXISTS idx_event_surveys_canonical ON cgcs.event_surveys(canonical_event_id);
CREATE INDEX IF NOT EXISTS idx_event_surveys_submitted ON cgcs.event_surveys(submitted_at);

-- --- Reservations indexes for impact rollups ------------------------------

CREATE INDEX IF NOT EXISTS idx_reservations_category ON cgcs.reservations(event_category);
CREATE INDEX IF NOT EXISTS idx_reservations_subtype ON cgcs.reservations(event_subtype);
CREATE INDEX IF NOT EXISTS idx_reservations_location ON cgcs.reservations(event_location);
CREATE INDEX IF NOT EXISTS idx_reservations_canonical ON cgcs.reservations(canonical_event_id);
-- Migration 012: structured CGCS Lead + free-form source_metadata blob.
-- cgcs_lead is called out separately because it's the most important "who"
-- field — Austin/Bryan/Cate/Marisela/Stefano. source_metadata holds every
-- other source-row field (Ad Astra #, Floor Layout, AV/Catering, Walkthrough
-- Date, full calendar description, etc.) without needing a column per field.

ALTER TABLE cgcs.reservations
    ADD COLUMN IF NOT EXISTS cgcs_lead VARCHAR(255),
    ADD COLUMN IF NOT EXISTS source_metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_reservations_cgcs_lead
    ON cgcs.reservations(LOWER(cgcs_lead));
-- Migration 013: CGCS Fogg Ledger budget tables.
-- Mirror of the spreadsheet so the dashboard can render Burn Rate, FY summary,
-- category rollups, and a full transactions list against real Postgres data.

CREATE TABLE IF NOT EXISTS cgcs.fiscal_years (
    fy_label VARCHAR(32) PRIMARY KEY,         -- "FY 2025-2026"
    start_date DATE NOT NULL,                 -- Sep 1
    end_date DATE NOT NULL,                   -- Aug 31 of following year
    starting_balance NUMERIC(12,2) NOT NULL,
    holdover_to_next NUMERIC(12,2),           -- earmarked carry-forward (e.g. $81k for FY26-27)
    is_current BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cgcs.ledger_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fy_label VARCHAR(32) NOT NULL REFERENCES cgcs.fiscal_years(fy_label),
    transaction_date DATE,
    description TEXT NOT NULL,
    category VARCHAR(64),                     -- Office Equipment, Event Expenses, Event Income,
                                              -- Subscription, Wage, Food, Miscellaneous, Police Coverage
    payment_method VARCHAR(64),               -- P-Card, Workday, etc.
    expense NUMERIC(12,2),
    revenue NUMERIC(12,2),
    running_balance NUMERIC(12,2),
    transfer_required BOOLEAN,
    transfer_confirmed BOOLEAN,
    notes TEXT,
    source_tag VARCHAR(64),                   -- "TBD", "Added (Notes)", original Source col
    -- Tie to a reservation when the description matches an event we know about
    linked_reservation_id UUID REFERENCES cgcs.reservations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_fy ON cgcs.ledger_transactions(fy_label);
CREATE INDEX IF NOT EXISTS idx_ledger_category ON cgcs.ledger_transactions(category);
CREATE INDEX IF NOT EXISTS idx_ledger_date ON cgcs.ledger_transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_ledger_reservation ON cgcs.ledger_transactions(linked_reservation_id);
"""
