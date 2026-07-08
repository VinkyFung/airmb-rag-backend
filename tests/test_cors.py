from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_preflight_for_rebuild_embeddings() -> None:
    response = client.options(
        "/api/v1/faqs/embeddings/rebuild",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

