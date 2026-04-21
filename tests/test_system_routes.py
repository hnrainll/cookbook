"""Tests for system routes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.media import router as media_router
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

    def test_media_image_route_serves_file(self, tmp_path, monkeypatch):
        image_dir = tmp_path / "images"
        image_dir.mkdir()
        image_file = image_dir / "test.jpg"
        image_file.write_bytes(b"image-bytes")

        monkeypatch.setattr("app.routes.media.IMAGE_DIR", image_dir)

        app = FastAPI()
        app.include_router(media_router)

        client = TestClient(app)
        response = client.get("/media/images/test.jpg")

        assert response.status_code == 200
        assert response.content == b"image-bytes"
        assert response.headers["content-type"] == "image/jpeg"

    def test_media_image_route_supports_head(self, tmp_path, monkeypatch):
        image_dir = tmp_path / "images"
        image_dir.mkdir()
        image_file = image_dir / "test.jpg"
        image_file.write_bytes(b"image-bytes")

        monkeypatch.setattr("app.routes.media.IMAGE_DIR", image_dir)

        app = FastAPI()
        app.include_router(media_router)

        client = TestClient(app)
        response = client.head("/media/images/test.jpg")

        assert response.status_code == 200
        assert response.content == b""
        assert response.headers["content-type"] == "image/jpeg"

    def test_media_image_route_rejects_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.routes.media.IMAGE_DIR", tmp_path)

        app = FastAPI()
        app.include_router(media_router)

        client = TestClient(app)
        response = client.get("/media/images/missing.jpg")

        assert response.status_code == 404
