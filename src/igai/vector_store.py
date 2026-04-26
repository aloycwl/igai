from __future__ import annotations

import os
from typing import Any, Dict, List

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from qdrant_client.models import PayloadSchemaType


DEFAULT_COLLECTION = "health_embeddings"


def get_qdrant_client() -> QdrantClient:
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")

    if not qdrant_url:
        raise ValueError("QDRANT_URL is required")

    return QdrantClient(url=qdrant_url, api_key=qdrant_api_key)


def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int) -> None:
    collections = client.get_collections().collections
    exists = any(collection.name == collection_name for collection in collections)

    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        client.create_payload_index(
            collection_name=collection_name,
            field_name="user_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )


def upsert_vector(
    id: str,
    vector: List[float],
    metadata: Dict[str, Any],
    collection_name: str = DEFAULT_COLLECTION,
) -> None:
    client = get_qdrant_client()
    ensure_collection(client=client, collection_name=collection_name, vector_size=len(vector))

    point = PointStruct(id=id, vector=vector, payload=metadata or {})
    client.upsert(collection_name=collection_name, points=[point])
