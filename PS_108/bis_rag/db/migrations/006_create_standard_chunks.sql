-- Migration 006: standard_chunks
-- Text chunks from PDF documents for future RAG retrieval.
-- embedding is NULL until the embedding step runs.
-- Dimension 1536 — update via migration if model changes.
--
-- IVFFlat index is commented out: it requires existing data to build centroids.
-- Run after embeddings are populated:
--   CREATE INDEX idx_chunks_embedding ON standard_chunks
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS standard_chunks (
    id                   BIGSERIAL PRIMARY KEY,
    standard_document_id BIGINT NOT NULL REFERENCES standard_documents(id) ON DELETE CASCADE,
    standard_id          BIGINT NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    chunk_text           TEXT NOT NULL,
    chunk_index          INTEGER NOT NULL,
    metadata             JSONB NOT NULL DEFAULT '{}',
    embedding            vector(1536),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (standard_document_id, chunk_index)
);

CREATE INDEX idx_chunks_standard_id  ON standard_chunks(standard_id);
CREATE INDEX idx_chunks_document_id  ON standard_chunks(standard_document_id);
