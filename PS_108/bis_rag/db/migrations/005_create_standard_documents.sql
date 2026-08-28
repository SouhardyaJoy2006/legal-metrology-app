-- Migration 005: standard_documents
-- Tracks physical documents (PDFs) for future ingestion.
-- availability_status: 'pending' | 'available' | 'not_available' | 'error'

CREATE TABLE IF NOT EXISTS standard_documents (
    id                  BIGSERIAL PRIMARY KEY,
    standard_id         BIGINT NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    document_type       TEXT NOT NULL DEFAULT 'full_standard',
    source_url          TEXT,
    local_path          TEXT,
    file_size_bytes     BIGINT,
    file_sha256         TEXT,
    availability_status TEXT NOT NULL DEFAULT 'pending' CHECK (availability_status IN (
                            'pending', 'available', 'not_available', 'error'
                        )),
    metadata            JSONB NOT NULL DEFAULT '{}',
    fetched_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_docs_standard_id ON standard_documents(standard_id);
CREATE INDEX idx_docs_status      ON standard_documents(availability_status);
CREATE INDEX idx_docs_type        ON standard_documents(document_type);
