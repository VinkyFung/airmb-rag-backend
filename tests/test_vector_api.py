from typing import Any

from fastapi.testclient import TestClient

from app.api.v1.endpoints.vector import vector_store_service
from app.main import app

client = TestClient(app)


async def fake_health() -> dict[str, Any]:
    return {
        "provider": "qdrant",
        "url": "http://127.0.0.1:6333",
        "collection": "airmb_faq_vectors",
        "collection_exists": True,
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimension": 1024,
        "collections": ["airmb_faq_vectors"],
    }


async def fake_ensure_collection() -> dict[str, Any]:
    return {
        "provider": "qdrant",
        "collection": "airmb_faq_vectors",
        "created": False,
        "embedding_dimension": 1024,
        "distance": "Cosine",
    }


def test_vector_health(monkeypatch) -> None:
    monkeypatch.setattr(vector_store_service, "health", fake_health)

    response = client.get("/api/v1/vector/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["status"] == "ok"
    assert body["data"]["collection"] == "airmb_faq_vectors"
    assert body["data"]["embedding_dimension"] == 1024


def test_ensure_vector_collection(monkeypatch) -> None:
    monkeypatch.setattr(vector_store_service, "ensure_collection", fake_ensure_collection)

    response = client.post("/api/v1/vector/collections/ensure")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["collection"] == "airmb_faq_vectors"
    assert body["data"]["created"] is False

