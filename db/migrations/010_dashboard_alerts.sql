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
