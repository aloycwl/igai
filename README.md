# IGAI Health Data Processing

Production-oriented backend utilities for processing health JSON records, creating embedding text, storing vectors in Qdrant, generating pandas analysis scripts from natural language, generating structured health reports, and running Supabase→IPFS→Neon sync jobs.

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
        ├── reporting.py          # aggregated metrics -> report dict
        ├── sync.py               # Supabase + IPFS + Neon sync orchestration
        └── cli.py                # command line entrypoint for sync
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

- `SUPABASE_URL`: Supabase endpoint (source)
- `SUPABASE_SERVICE_KEY`: Supabase service role key
- `TARGET_DATABASE_URL`: Neon/Postgres SQLAlchemy URL (target)
- `QDRANT_URL`: Qdrant endpoint (optional)
- `QDRANT_API_KEY`: Qdrant API key (optional)
- `QDRANT_COLLECTION`: vector collection name (optional)

## Sync Behavior

`run_sync` reads `public.igai` from Supabase with:
- `type = 1`
- `id > last_synced_id` (loaded from `sync.json`)
- ordered by `id asc`

For each row:
1. download `https://<cid>.ipfs.w3s.link/`
2. normalize payload
3. write/upsert to Neon target table (`health_records` default)
4. optionally upsert vector into Qdrant when `qdrant_collection` is provided

It then updates `sync.json` with the newest processed id.

No retries are included by design.

## Running Sync

Programmatic:

```python
from igai import run_sync

result = run_sync(
    sync_state_path="sync.json",
    batch_size=200,
    target_table="health_records",
    qdrant_collection=None,
)
print(result)
```

CLI:

```bash
igai-sync --state-file sync.json --batch-size 200 --target-table health_records
```

## Usage (Core Functions)

```python
from igai import (
    normalize_record,
    to_embedding_text,
    upsert_vector,
    generate_analysis_script,
    build_health_report,
)

row = normalize_record({})
text = to_embedding_text(row)
script = generate_analysis_script("Show average heart rate trend over last 7 days")
report = build_health_report({"heart_rate_avg": 78})
```
