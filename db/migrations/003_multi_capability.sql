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
