-- Migration 004: standard_relationships
-- Directed relationships between standards.
-- Populated in a future step when relationship extraction is implemented.
--
-- relationship_type supported values:
--   supersedes | equivalent_to | normative_reference | terminology_reference
--   safety_reference | installation_reference | other_reference
--
-- target_standard_id is NULL when the target is not yet in the DB.
-- target_standard_number_raw preserves the original string in that case.

CREATE TABLE IF NOT EXISTS standard_relationships (
    id                         BIGSERIAL PRIMARY KEY,
    source_standard_id         BIGINT NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    target_standard_id         BIGINT REFERENCES standards(id) ON DELETE SET NULL,
    target_standard_number_raw TEXT,
    relationship_type          TEXT NOT NULL CHECK (relationship_type IN (
                                   'supersedes',
                                   'equivalent_to',
                                   'normative_reference',
                                   'terminology_reference',
                                   'safety_reference',
                                   'installation_reference',
                                   'other_reference'
                               )),
    source_field               TEXT,
    metadata                   JSONB NOT NULL DEFAULT '{}',
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_standard_id, target_standard_number_raw, relationship_type)
);

CREATE INDEX idx_rel_source      ON standard_relationships(source_standard_id);
CREATE INDEX idx_rel_target      ON standard_relationships(target_standard_id);
CREATE INDEX idx_rel_type        ON standard_relationships(relationship_type);
CREATE INDEX idx_rel_source_type ON standard_relationships(source_standard_id, relationship_type);
