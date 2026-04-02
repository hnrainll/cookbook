"""Tests for system routes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.system import router


class TestSystemRoutes:
    def test_root_route(self):
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "running"
        assert "platforms" in payload

    def test_health_route(self):
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
