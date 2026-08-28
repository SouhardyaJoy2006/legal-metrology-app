"""
bis_rag — BIS Indian Standards RAG Backend
==========================================

Subsystem layout:
    bis_rag.config          — environment-variable based configuration
    bis_rag.db              — PostgreSQL connection and migration runner
    bis_rag.preprocessing   — raw → canonical JSON preprocessing pipeline
    bis_rag.ingestion       — DB loader (stub; activated after embedding step)
    bis_rag.tests           — unit tests for normalization and validation
"""
