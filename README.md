# IGAI Health Data Processing

Production-oriented backend utilities for processing health JSON records, creating embedding text, storing vectors in Qdrant, generating pandas analysis scripts from natural language, and creating structured health reports.

## Project Structure

```text
igai/
├── .env.sample
├── pyproject.toml
├── README.md
└── src/
    └── igai/
        ├── __init__.py
        ├── normalization.py      # JSON -> flat PostgreSQL row
        ├── embedding_text.py     # normalized record -> embedding text
        ├── vector_store.py       # Qdrant collection + upsert
        ├── query_codegen.py      # natural language -> pandas script
        └── reporting.py          # aggregated metrics -> report dict
```

## Setup

1. Create and activate a virtual environment.
2. Install package dependencies:
   ```bash
   pip install -e .
   ```
3. Copy env template and configure:
   ```bash
   cp .env.sample .env
   ```

## Environment Variables

- `QDRANT_URL`: Qdrant endpoint (required)
- `QDRANT_API_KEY`: Qdrant API key (optional for local, required for cloud)
- `QDRANT_COLLECTION`: default collection name (optional)
- `QDRANT_CLOUD_INFERENCE`: set `true` to let Qdrant run inference for `Document(...)` payloads (default: `true`)
- `SUPABASE_URL`: Supabase project URL for source rows
- `SUPABASE_SERVICE_KEY`: Supabase service role key for REST reads
- `TARGET_DATABASE_URL`: Neon/PostgreSQL SQLAlchemy connection URL

## Usage

```python
from igai import (
    normalize_record,
    to_embedding_text,
    upsert_vector,
    generate_analysis_script,
    build_health_report,
)

raw = {
    "vitalSigns": {
        "heartRate": 96.2,
        "spo2": 98.3,
        "respiratoryRate": 28.2,
        "stressScore": 46.6,
        "hrvSdnn": 81.8,
        "hrvRmssd": 56,
        "bloodPressureSystolic": 110,
        "bloodPressureDiastolic": 60,
    },
    "holisticHealth": {"generalWellness": 80.3},
    "risks": {"cardiovascularRisks": {"generalRisk": 7.84, "stroke": 4.94}},
}

row = normalize_record(raw)
text = to_embedding_text(row)

# vector = [0.01, 0.03, ...]
# upsert_vector(id="record-1", vector=vector, metadata=row)

script = generate_analysis_script("Show average heart rate trend over last 7 days")

report = build_health_report({
    "heart_rate_avg": 78,
    "spo2_avg": 97.9,
    "stress_score_avg": 42,
    "cardiovascular_risk_avg": 5.1,
    "general_wellness_avg": 81,
})
```

### Sync Supabase -> IPFS JSON -> Neon + Qdrant BM25

The sync runner reads rows from Supabase (`type=1`), fetches JSON from IPFS by `cid`, normalizes + upserts into Neon, and (optionally) upserts text to Qdrant using cloud inference with model `qdrant/bm25`.

Run one batch:

```bash
python -m igai.cli \
  --state-file sync.json \
  --batch-size 200 \
  --target-table health_records \
  --qdrant-collection health_embeddings
```

Run continuously (one-by-one with batch size 1):

```bash
python -m igai.cli \
  --batch-size 1 \
  --qdrant-collection health_embeddings \
  --continuous \
  --sleep-seconds 2
```

Notes:
- `--state-file` tracks the latest synced Supabase `id` so restarts continue from where they stopped.
- Set `--batch-size 1` if you want strict one-by-one ingestion.
- Omit `--qdrant-collection` if you only want Neon storage.

## Notes

- `normalize_record` uses safe dict access and returns `None` for missing values (PostgreSQL `NULL`).
- `to_embedding_text` always includes all schema fields and uses `unknown` placeholders.
- `upsert_vector` ensures collection existence and uses cosine similarity for dense vectors.
- `upsert_bm25_document` creates a sparse BM25-compatible collection and uploads `Document(text=..., model="qdrant/bm25")` so inference is provided by Qdrant cloud.
- `generate_analysis_script` supports trend, aggregation, and cohort comparison patterns.
- `build_health_report` uses cautious language and avoids diagnosis statements.
