from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, Document, PointStruct, SparseVectorParams, VectorParams
from qdrant_client.models import Modifier, PayloadSchemaType


DEFAULT_COLLECTION = "health_embeddings"


def get_qdrant_client() -> QdrantClient:
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")
    cloud_inference = os.environ.get("QDRANT_CLOUD_INFERENCE", "true").lower() == "true"

    if not qdrant_url:
        raise ValueError("QDRANT_URL is required")

    return QdrantClient(url=qdrant_url, api_key=qdrant_api_key, cloud_inference=cloud_inference)


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


def ensure_bm25_collection(client: QdrantClient, collection_name: str, vector_name: str = "text") -> None:
    collections = client.get_collections().collections
    exists = any(collection.name == collection_name for collection in collections)

    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config={},
            sparse_vectors_config={vector_name: SparseVectorParams(modifier=Modifier.IDF)},
        )


def upsert_vector(
    id: str,
    vector: List[float],
    metadata: Dict[str, Any],
    collection_name: str = DEFAULT_COLLECTION,
    client: Optional[QdrantClient] = None,
) -> None:
    client = client or get_qdrant_client()
    ensure_collection(client=client, collection_name=collection_name, vector_size=len(vector))

    point = PointStruct(id=id, vector=vector, payload=metadata or {})
    client.upsert(collection_name=collection_name, points=[point])


def upsert_bm25_document(
    id: str,
    text: str,
    metadata: Dict[str, Any],
    collection_name: str = DEFAULT_COLLECTION,
    vector_name: str = "text",
    model: str = "qdrant/bm25",
    client: Optional[QdrantClient] = None,
) -> None:
    client = client or get_qdrant_client()
    ensure_bm25_collection(client=client, collection_name=collection_name, vector_name=vector_name)

    point = PointStruct(
        id=id,
        vector={vector_name: Document(text=text, model=model)},
        payload=metadata or {},
    )
    client.upsert(collection_name=collection_name, points=[point])
