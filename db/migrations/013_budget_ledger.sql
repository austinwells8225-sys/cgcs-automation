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
