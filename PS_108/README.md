# BIS Standards Retrieval-Augmented Generation (RAG) Subsystem

> **SIH 2026 Problem Statement 108** — AI-Powered Retrieval and Recommendation Engine for Bureau of Indian Standards (BIS) Technical Specifications.

---

## 1. Overview
The **BIS RAG Subsystem** is a domain-specific Retrieval-Augmented Generation (RAG) backend engine for Indian Standards published by the **Bureau of Indian Standards (BIS)**. It provides high-precision hybrid semantic and lexical retrieval, version family lifecycle resolution, metadata-aware scoring, and multi-lingual (English + Devanagari Hindi) search across engineering standard datasets.

---

## 2. Project Scope & Datasets
- **Current Technical Scope**:
  - **Mechanical Engineering Department (MED)**: 1,460 standard records.
  - **Production and General Engineering Department (PGD)**: 2,674 standard records.
  - **Combined Dataset Total**: **4,134 standards**, **725 amendments**, and **15 resolved superseding parent-child relationships**.
- **Embedding Model**: `BAAI/bge-m3` (1024-dimensional dense vector embeddings with native cross-lingual support for English and Hindi).
- **Vector Database**: PostgreSQL 18 with `pgvector` (`vector(1024)` extension).

---

## 3. Repository Directory Structure

```
Team_Project/
└── PS_108/
    ├── bis_rag/                    # Core Python RAG subsystem package
    │   ├── db/                     # Connection manager & SQL migrations (001 -> 009)
    │   ├── embeddings/             # BGE-M3 model registry, text builder, GPU embedder
    │   ├── ingestion/              # PostgreSQL loader & superseding FK resolver
    │   ├── preprocessing/          # Normalizer, validator, and JSONL pipeline
    │   └── retrieval/              # Hybrid retrieval, lifecycle resolution & ranking
    │       ├── search.py           # search_standards() main high-level API
    │       ├── semantic.py         # BGE-M3 pgvector cosine distance search
    │       ├── lexical.py          # PostgreSQL full-text & exact code search
    │       ├── merge.py            # Candidate pool merging
    │       ├── lifecycle.py        # Version family grouping & current/superseded pointers
    │       └── ranking.py          # Metadata-aware scoring layer
    ├── data/
    │   ├── raw/                    # Scraped JSONL datasets (MED & PGD)
    │   └── processed/              # Canonical preprocessed JSON & quality reports
    ├── docs/                       # Architectural guides & evaluation documentation
    ├── scripts/
    │   ├── setup_db.sh             # PostgreSQL database setup script
    │   ├── load_data.py            # Data ingestion runner
    │   ├── create_embeddings.py    # GPU BGE-M3 vector embedding pipeline
    │   └── cli.py                  # Interactive REPL terminal interface
    ├── .env                        # Local database & model environment config
    ├── README.md                   # System documentation
    └── requirements_bis_rag.txt    # Subsystem Python dependencies
```

---

## 4. Key Subsystem Components

### A. Document Embedding Representation (`bis_rag.embeddings.builder`)
Constructs rich semantic text representations for each standard including:
- Standard Number & Full Title
- Type of Standard (*Safety Standard, Code of Practice, Product Specification*)
- Department & Technical Committee (*MED 40*, *PGD 25*)
- Classification Group (`std_group` > `sub_group` > `sub_sub_group`)
- ICS International Classification Code
- ISO/IEC Equivalent Standards
- Superseded Standard Pointers & Common Names

### B. Hybrid Retrieval Pipeline (`bis_rag.retrieval`)
1. **Semantic Search (`semantic.py`)**: BGE-M3 1024-dim dense vector search via pgvector `<=>` cosine distance ($k_{\text{retrieval}}=30$).
2. **Lexical Search (`lexical.py`)**: Exact match on standard numbers (`IS 16810`), ISO equivalents (`ISO 13849`), ICS codes, and PostgreSQL full-text title search.
3. **Candidate Merging (`merge.py`)**: Combines vector and lexical candidate pools by standard ID.
4. **Lifecycle & Family Resolution (`lifecycle.py`)**:
   - Groups standards into version families (e.g. `IS 16810 (Part 1)`).
   - Identifies active `CURRENT` standards (e.g. `IS 16810 (Part 1):2026`).
   - Marks older editions as `SUPERSEDED` (`IS 16810 (Part 1):2018`) and attaches explicit pointers to the latest version.
5. **Metadata-Aware Scoring (`ranking.py`)**:
   $$Score = w_{\text{vector}} \cdot S_{\text{vec}} + w_{\text{lexical}} \cdot S_{\text{lex}} + \text{Bonus}_{\text{current}} + \text{Bonus}_{\text{type}} + \text{Boost}_{\text{exact}}$$

---

## 5. Running Instructions

### 1. Database Connection Check
```bash
cd "PS_108"
source ../.venv/bin/activate

# Verify PostgreSQL connection and pgvector extension
python -m bis_rag.db.manage ping
```

### 2. Launch Interactive Terminal CLI
```bash
python scripts/cli.py
```

#### Interactive CLI Commands:
```text
bis> status
bis> search safety of machinery
bis> search IS 16810 Part 1
bis> get IS 16810 (Part 1):2026
bis> list --type Safety Standard --n 10
bis> stats
```

---

## 6. High-Level Python API Usage (`search_standards`)

```python
from bis_rag.retrieval import search_standards

results = search_standards(
    query="safety-related parts of control systems",
    top_k=8,
    include_superseded=True
)

for r in results:
    print(f"{r['standard_number']} | Match: {r['relevance_percentage']}% | Status: {r['status_label']}")
    if r['latest_version']:
        print(f"  -> Superseded! Active version is {r['latest_version']['standard_number']}")
```

---

## 7. Future System Roadmap
1. **Technical Standard PDF Ingestion**: Extracting and chunking full PDF document text into `standard_chunks`.
2. **REST API & Web UI**: Exposing `search_standards()` via a Flask REST API for frontend consumption.
