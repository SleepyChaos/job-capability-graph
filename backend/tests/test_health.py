from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app


def test_health_endpoint_returns_database_status() -> None:
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"
    assert response.headers["X-Request-ID"]
