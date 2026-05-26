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
