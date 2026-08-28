-- Migration 003: standard_amendments
-- Stores each amendment as one row. The raw JSONB blob is kept for safety
-- because amendment structure in the real data varies (some have empty descriptions).

CREATE TABLE IF NOT EXISTS standard_amendments (
    id               BIGSERIAL PRIMARY KEY,
    standard_id      BIGINT NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    amendment_number TEXT,
    amendment_date   TEXT,   -- stored as text: real data has "2026" (year only)
    amendment_title  TEXT,
    raw_data         JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_amendments_standard_id ON standard_amendments(standard_id);
CREATE INDEX idx_amendments_number      ON standard_amendments(standard_id, amendment_number);
