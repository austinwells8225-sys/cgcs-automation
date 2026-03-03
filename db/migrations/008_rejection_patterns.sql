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
