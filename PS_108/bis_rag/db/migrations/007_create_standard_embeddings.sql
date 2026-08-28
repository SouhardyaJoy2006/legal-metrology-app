-- Migration 007: standard_embeddings
-- One metadata-level embedding per standard (separate from PDF chunks).
-- embedding_text stores the string that was fed to the model (for auditability).
-- embedding is NULL until the embedding step runs.
--
-- IVFFlat index — run after embeddings are populated:
--   CREATE INDEX idx_std_embeddings_embedding ON standard_embeddings
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS standard_embeddings (
    id             BIGSERIAL PRIMARY KEY,
    standard_id    BIGINT NOT NULL UNIQUE REFERENCES standards(id) ON DELETE CASCADE,
    embedding_text TEXT,
    embedding      vector(1536),
    model_name     TEXT,
    embedded_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
