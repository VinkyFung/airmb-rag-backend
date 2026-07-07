from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.exceptions import register_exception_handlers


def test_operational_error_returns_service_unavailable() -> None:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/database-error")
    async def raise_database_error() -> None:
        raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get("/database-error")

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"

