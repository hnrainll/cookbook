"""Tests for static page routes."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.routes.pages import router


class TestPages:
    def test_privacy_policy_page(self):
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/meta/privacy")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Privacy Policy" in response.text
        assert settings.public_contact_email in response.text

    def test_data_deletion_page(self):
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/meta/data-deletion")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Data Deletion Instructions" in response.text

    def test_pages_use_configured_contact_email(self):
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        with patch("app.routes.pages.settings.public_contact_email", "public@example.test"):
            response = client.get("/meta/privacy")

        assert response.status_code == 200
        assert "public@example.test" in response.text
