"""Tests for auth and callback routes"""

import pytest
from fastapi.testclient import TestClient

from app.core.auth import AuthService
from app.core.reply import ReplyService


@pytest.fixture(autouse=True)
def reset_singletons():
    AuthService.reset_instance()
    ReplyService.reset_instance()
    yield
    AuthService.reset_instance()
    ReplyService.reset_instance()


class MockHandler:
    async def gen_auth_url(self, user_id):
        return "https://example.com/auth"

    async def handle_callback(self, params):
        if params.get("oauth_token") == "valid":
            return "授权成功", "user1"
        return "授权失败", None

    async def remove_auth(self, user_id):
        return True


class TestOAuthCallback:
    def test_missing_oauth_token(self):
        """Missing oauth_token returns error."""
        from fastapi import FastAPI

        from app.routes.auth import router

        app = FastAPI()
        app.include_router(router)

        AuthService.create_instance()
        ReplyService.create_instance()

        client = TestClient(app)
        response = client.get("/auth")
        assert response.status_code == 200
        data = response.json()
        assert "缺少" in data["message"]

    def test_auth_service_not_initialized(self):
        """AuthService not initialized returns error."""
        from fastapi import FastAPI

        from app.routes.auth import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/auth?oauth_token=test")
        assert response.status_code == 200
        data = response.json()
        assert "未初始化" in data["message"]

    def test_callback_with_platform(self):
        """OAuth callback routes to correct platform handler."""
        from fastapi import FastAPI

        from app.routes.auth import router

        app = FastAPI()
        app.include_router(router)

        auth_svc = AuthService.create_instance()
        reply_svc = ReplyService.create_instance()

        auth_svc.register("fanfou", MockHandler())

        sent = []
        from app.schemas.event import MessageSource

        reply_svc.register(
            MessageSource.FEISHU,
            reply_handler=lambda m, t: None,
            send_handler=lambda uid, text: sent.append((uid, text)),
        )

        client = TestClient(app)
        response = client.get("/auth?platform=fanfou&oauth_token=valid")
        assert response.status_code == 200
        data = response.json()
        assert "成功" in data["message"]

    def test_callback_default_platform(self):
        """Default platform is fanfou when not specified."""
        from fastapi import FastAPI

        from app.routes.auth import router

        app = FastAPI()
        app.include_router(router)

        auth_svc = AuthService.create_instance()
        ReplyService.create_instance()

        callbacks = []

        class TrackingHandler:
            async def gen_auth_url(self, user_id):
                return ""

            async def handle_callback(self, params):
                callbacks.append(params)
                return "ok", None

            async def remove_auth(self, user_id):
                return True

        auth_svc.register("fanfou", TrackingHandler())

        client = TestClient(app)
        client.get("/auth?oauth_token=tok123")

        assert len(callbacks) == 1
        assert callbacks[0]["oauth_token"] == "tok123"

    def test_threads_callback_returns_ok(self):
        from fastapi import FastAPI

        from app.services.platforms.threads.handler import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/callback/threads?type=delete")
        assert response.status_code == 200
        assert response.json()["message"] == "ok"
