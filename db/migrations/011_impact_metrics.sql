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
