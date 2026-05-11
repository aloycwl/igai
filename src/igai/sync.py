from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, MetaData, String, Table, create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .embedding_text import to_embedding_text
from .normalization import normalize_record

from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Document

DEFAULT_SYNC_STATE_FILE = "sync.json"
DEFAULT_TARGET_TABLE = "health_records"
IPFS_FETCH_WORKERS = 8

_engine_table_cache: Dict[str, Tuple[Any, Table]] = {}
_qdrant_client_cache: Optional[QdrantClient] = None


def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    request = Request(url=url, method="GET", headers=headers or {})
    retry_delays = [1, 5, 15]

    for attempt, delay in enumerate([0] + retry_delays):
        if delay > 0:
            time.sleep(delay)
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            if attempt == len(retry_delays):
                raise
            print(f"[WARNING] HTTP GET failed (attempt {attempt+1}/{len(retry_delays)+1}): {type(e).__name__}: {e}")


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
    gateways = [
        f"https://{cid}.ipfs.w3s.link/",
        f"https://cloudflare-ipfs.com/ipfs/{cid}/",
        f"https://ipfs.io/ipfs/{cid}/",
        f"https://dweb.link/ipfs/{cid}/"
    ]

    last_exception = None
    for url in gateways:
        print(f"[DEBUG] Trying IPFS CID via: {url}")
        try:
            data = _http_get_json(url)
            if not isinstance(data, dict):
                raise ValueError(f"IPFS payload for cid={cid} via {url} is not a JSON object")
            return data
        except Exception as e:
            print(f"[DEBUG] Failed to fetch {url}: {e}")
            last_exception = e

    raise ValueError(f"All gateways failed for cid={cid}. Last error: {last_exception}")


def _fetch_ipfs_parallel(
    rows: List[Dict[str, Any]], max_workers: int = IPFS_FETCH_WORKERS
) -> Dict[int, Optional[Dict[str, Any]]]:
    results: Dict[int, Optional[Dict[str, Any]]] = {}

    def _fetch_one(row: Dict[str, Any]) -> Tuple[int, Optional[Dict[str, Any]]]:
        source_id = int(row.get("id"))
        cid = row.get("cid")
        if not cid:
            return source_id, None
        try:
            return source_id, _fetch_ipfs_json(cid=cid)
        except Exception as e:
            print(f"[SKIP] Failed CID {cid}: {e}")
            return source_id, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_fetch_one, row) for row in rows]
        for future in as_completed(futures):
            source_id, payload = future.result()
            results[source_id] = payload

    return results


def _get_or_create_engine(target_database_url: str, table_name: str) -> Tuple[Any, Table]:
    cache_key = f"{target_database_url}|{table_name}"
    if cache_key in _engine_table_cache:
        return _engine_table_cache[cache_key]

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
    _engine_table_cache[cache_key] = (engine, table)
    return engine, table


def _get_qdrant_client() -> QdrantClient:
    global _qdrant_client_cache
    if _qdrant_client_cache is not None:
        return _qdrant_client_cache
    _qdrant_client_cache = QdrantClient(
        url=os.environ.get("QDRANT_URL"),
        api_key=os.environ.get("QDRANT_API_KEY"),
        cloud_inference=True,
    )
    return _qdrant_client_cache


def _qdrant_upsert_batch(client: QdrantClient, collection_name: str, points: List[PointStruct]) -> None:
    retry_delays = [3, 10, 30]
    for attempt, delay in enumerate([0] + retry_delays):
        if delay > 0:
            time.sleep(delay)
        try:
            client.upsert(collection_name=collection_name, points=points)
            return
        except Exception as e:
            if attempt == len(retry_delays):
                print(f"[ERROR] Qdrant batch upsert failed permanently: {type(e).__name__}: {e}")
                raise
            print(f"[WARNING] Qdrant upsert failed (attempt {attempt+1}/{len(retry_delays)+1}): {type(e).__name__}: {e}")


def _qdrant_upsert_individual(client: QdrantClient, collection_name: str, points: List[PointStruct]) -> None:
    for point in points:
        retry_delays = [3, 10, 30]
        for attempt, delay in enumerate([0] + retry_delays):
            if delay > 0:
                time.sleep(delay)
            try:
                client.upsert(collection_name=collection_name, points=[point])
                break
            except Exception as e:
                if attempt == len(retry_delays):
                    print(f"[ERROR] Qdrant upsert failed permanently for id {point.id}: {type(e).__name__}: {e}")
                else:
                    print(f"[WARNING] Qdrant upsert failed (attempt {attempt+1}/{len(retry_delays)+1}) for id {point.id}: {type(e).__name__}: {e}")


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
        return {"synced": 0, "fetched": 0, "last_synced_id": last_synced_id}

    fetched_count = len(rows)
    max_synced_id = max(int(row.get("id")) for row in rows)

    ipfs_results = _fetch_ipfs_parallel(rows)

    engine, table = _get_or_create_engine(target_database_url=target_database_url, table_name=target_table)

    db_payloads: List[Dict[str, Any]] = []
    qdrant_points: List[PointStruct] = []
    synced_count = 0

    for row in rows:
        source_id = int(row.get("id"))
        raw_payload = ipfs_results.get(source_id)
        if raw_payload is None:
            continue

        normalized = normalize_record(raw_payload)
        embedding_text = to_embedding_text(normalized)
        external_id = int(source_id)

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
        db_payloads.append(insert_payload)

        if qdrant_collection:
            cid = row.get("cid")
            point = PointStruct(
                id=int(external_id),
                payload={
                    "source_id": source_id,
                    "cid": cid,
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
                },
                vector={
                    "embedding": Document(
                        text=embedding_text,
                        model="sentence-transformers/all-MiniLM-L6-v2",
                    )
                },
            )
            qdrant_points.append(point)

        synced_count += 1

    if db_payloads:
        with engine.begin() as conn:
            stmt = pg_insert(table).values(db_payloads)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=[table.c.external_id],
                set_={c.name: stmt.excluded[c.name] for c in table.columns if c.name != "external_id"},
            )
            conn.execute(upsert_stmt)

    if qdrant_collection and qdrant_points:
        client = _get_qdrant_client()
        try:
            _qdrant_upsert_batch(client, qdrant_collection, qdrant_points)
        except Exception:
            print("[FALLBACK] Batch upsert failed, retrying points individually...")
            _qdrant_upsert_individual(client, qdrant_collection, qdrant_points)

    _save_sync_state(sync_state_path=sync_state_path, last_synced_id=max_synced_id)

    return {
        "synced": synced_count,
        "fetched": fetched_count,
        "last_synced_id": max_synced_id,
        "state_file": sync_state_path,
        "target_table": target_table,
    }
