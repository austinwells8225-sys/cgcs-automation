-- CGCS Event Space Automation Engine
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

-- Indexes
CREATE INDEX idx_reservations_status ON cgcs.reservations(status);
CREATE INDEX idx_reservations_date ON cgcs.reservations(requested_date);
CREATE INDEX idx_reservations_email ON cgcs.reservations(requester_email);
CREATE INDEX idx_audit_trail_reservation ON cgcs.audit_trail(reservation_id);
CREATE INDEX idx_audit_trail_created ON cgcs.audit_trail(created_at);

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
