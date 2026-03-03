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
