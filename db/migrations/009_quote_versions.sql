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
