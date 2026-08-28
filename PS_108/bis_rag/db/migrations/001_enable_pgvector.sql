-- Migration 001: Enable pgvector extension
-- Run this first — all subsequent migrations depend on the vector type.
-- Requires PostgreSQL to have pgvector installed (apt: postgresql-xx-pgvector).

CREATE EXTENSION IF NOT EXISTS vector;
