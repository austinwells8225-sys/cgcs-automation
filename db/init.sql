-- CGCS Event Space Automation Engine
-- Bootstrap script for PostgreSQL initialization

-- Create application schema (separate from N8N's tables)
CREATE SCHEMA IF NOT EXISTS cgcs;

-- Set search path to include cgcs schema
ALTER DATABASE cgcs_events SET search_path TO cgcs, public;
