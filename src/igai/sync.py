from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, MetaData, String, Table, create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .embedding_text import to_embedding_text
from .normalization import normalize_record
from .vector_store import upsert_vector


DEFAULT_SYNC_STATE_FILE = "sync.json"
DEFAULT_TARGET_TABLE = "health_records"


def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    request = Request(url=url, method="GET", headers=headers or {})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_sync_state(sync_state_path: str) -> Dict[str, Any]:
    path = Path(sync_state_path)
    if not path.exists():
        return {"last_synced_id": 0}

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        return {"last_synced_id": 0}

    return {"last_synced_id": int(data.get("last_synced_id", 0) or 0)}


def _save_sync_state(sync_state_path: str, last_synced_id: int) -> None:
    path = Path(sync_state_path)
    payload = {"last_synced_id": int(last_synced_id)}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fetch_supabase_rows(
    supabase_url: str,
    supabase_key: str,
    after_id: int,
    limit: int,
) -> List[Dict[str, Any]]:
    params = {
        "select": "id,cid,addr,type,m,created_at",
        "type": "eq.1",
        "id": f"gt.{after_id}",
        "order": "id.asc",
        "limit": str(limit),
    }
    url = f"{supabase_url.rstrip('/')}/rest/v1/igai?{urlencode(params)}"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
    }

    data = _http_get_json(url, headers=headers)
    if not isinstance(data, list):
        return []
    return data


def _fetch_ipfs_json(cid: str) -> Dict[str, Any]:
    url = f"https://{cid}.ipfs.w3s.link/"
    data = _http_get_json(url)
    if not isinstance(data, dict):
        raise ValueError(f"IPFS payload for cid={cid} is not a JSON object")
    return data


def _get_target_table(target_database_url: str, table_name: str) -> tuple[Any, Table]:
    engine = create_engine(target_database_url, future=True)
    metadata = MetaData()

    table = Table(
        table_name,
        metadata,
        Column("external_id", String(64), primary_key=True),
        Column("source_id", BigInteger, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=True),
        Column("user_id", String(128), nullable=True),
        Column("timestamp", String(64), nullable=True),
        Column("heart_rate", Float, nullable=True),
        Column("spo2", Float, nullable=True),
        Column("respiratory_rate", Float, nullable=True),
        Column("stress_score", Float, nullable=True),
        Column("hrv_sdnn", Float, nullable=True),
        Column("hrv_rmssd", Float, nullable=True),
        Column("systolic_bp", Float, nullable=True),
        Column("diastolic_bp", Float, nullable=True),
        Column("cardiovascular_risk", Float, nullable=True),
        Column("stroke_risk", Float, nullable=True),
        Column("general_wellness", Float, nullable=True),
        Column("raw_payload", JSON, nullable=False),
    )

    metadata.create_all(engine)
    return engine, table


def run_sync(
    sync_state_path: str = DEFAULT_SYNC_STATE_FILE,
    batch_size: int = 200,
    target_table: str = DEFAULT_TARGET_TABLE,
    qdrant_collection: Optional[str] = None,
) -> Dict[str, Any]:
    """Sync type=1 rows from Supabase -> IPFS JSON -> Neon table (+optional Qdrant upsert)."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    target_database_url = os.environ.get("TARGET_DATABASE_URL")

    if not supabase_url:
        raise ValueError("SUPABASE_URL is required")
    if not supabase_key:
        raise ValueError("SUPABASE_SERVICE_KEY is required")
    if not target_database_url:
        raise ValueError("TARGET_DATABASE_URL is required (Neon/Postgres connection string)")

    state = _load_sync_state(sync_state_path)
    last_synced_id = int(state.get("last_synced_id", 0))

    rows = _fetch_supabase_rows(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        after_id=last_synced_id,
        limit=batch_size,
    )

    if not rows:
        return {"synced": 0, "last_synced_id": last_synced_id}

    engine, table = _get_target_table(target_database_url=target_database_url, table_name=target_table)

    synced_count = 0
    max_synced_id = last_synced_id

    with engine.begin() as conn:
        for row in rows:
            source_id = int(row.get("id"))
            cid = row.get("cid")
            if not cid:
                max_synced_id = max(max_synced_id, source_id)
                continue

            raw_payload = _fetch_ipfs_json(cid=cid)
            normalized = normalize_record(raw_payload)
            embedding_text = to_embedding_text(normalized)
            external_id = f"igai-{source_id}"

            insert_payload = {
                "external_id": external_id,
                "source_id": source_id,
                "created_at": row.get("created_at"),
                "user_id": normalized.get("user_id"),
                "timestamp": normalized.get("timestamp"),
                "heart_rate": normalized.get("heart_rate"),
                "spo2": normalized.get("spo2"),
                "respiratory_rate": normalized.get("respiratory_rate"),
                "stress_score": normalized.get("stress_score"),
                "hrv_sdnn": normalized.get("hrv_sdnn"),
                "hrv_rmssd": normalized.get("hrv_rmssd"),
                "systolic_bp": normalized.get("systolic_bp"),
                "diastolic_bp": normalized.get("diastolic_bp"),
                "cardiovascular_risk": normalized.get("cardiovascular_risk"),
                "stroke_risk": normalized.get("stroke_risk"),
                "general_wellness": normalized.get("general_wellness"),
                "raw_payload": raw_payload,
            }
            stmt = pg_insert(table).values(insert_payload)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=[table.c.external_id],
                set_=insert_payload,
            )
            conn.execute(upsert_stmt)

            if qdrant_collection:
                vector = [float(len(embedding_text))]
                upsert_vector(
                    id=external_id,
                    vector=vector,
                    metadata={"source_id": source_id, "cid": cid, "text": embedding_text},
                    collection_name=qdrant_collection,
                )

            synced_count += 1
            max_synced_id = max(max_synced_id, source_id)

    _save_sync_state(sync_state_path=sync_state_path, last_synced_id=max_synced_id)

    return {
        "synced": synced_count,
        "last_synced_id": max_synced_id,
        "state_file": sync_state_path,
        "target_table": target_table,
    }
