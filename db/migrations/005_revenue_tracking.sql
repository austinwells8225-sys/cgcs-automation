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
