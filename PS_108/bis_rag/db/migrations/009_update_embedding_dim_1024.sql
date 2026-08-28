-- Migration 009: update embedding columns to 1024 dims for BGE-M3 / multilingual-e5
-- Run this before generating any embeddings.
-- Safe to run when no embeddings exist yet (column is NULL).
--
-- If you later switch to a different dimension, create migration 010.

ALTER TABLE standard_embeddings
    DROP COLUMN IF EXISTS embedding,
    ADD  COLUMN embedding vector(1024);

ALTER TABLE standard_chunks
    DROP COLUMN IF EXISTS embedding,
    ADD  COLUMN embedding vector(1024);
