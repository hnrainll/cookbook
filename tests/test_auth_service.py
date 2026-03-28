"""Tests for AuthService"""

import asyncio

from app.core.auth import AuthService


class MockAuthHandler:
    def __init__(self):
        self.auth_urls = {}
        self.removed = set()

    async def gen_auth_url(self, user_id: str) -> str:
        url = f"https://example.com/auth?user={user_id}"
        self.auth_urls[user_id] = url
        return url

    async def handle_callback(self, params: dict) -> tuple[str, str | None]:
        token = params.get("oauth_token")
        if token == "valid_token":
            return "授权成功", "user1"
        return "授权失败", None

    async def remove_auth(self, user_id: str) -> bool:
        self.removed.add(user_id)
        return True


class TestAuthService:
    def setup_method(self):
        AuthService.reset_instance()

    def teardown_method(self):
        AuthService.reset_instance()

    def test_create_instance(self):
        svc = AuthService.create_instance()
        assert svc is not None
        assert AuthService.get_instance() is svc

    def test_register_and_list(self):
        svc = AuthService.create_instance()
        handler = MockAuthHandler()
        svc.register("fanfou", handler)
        assert "fanfou" in svc.list_platforms()

    def test_start_auth(self):
        loop = asyncio.new_event_loop()
        try:
            svc = AuthService.create_instance()
            handler = MockAuthHandler()
            svc.register("fanfou", handler)
            url = loop.run_until_complete(svc.start_auth("fanfou", "user1"))
            assert "user1" in url
        finally:
            loop.close()

    def test_start_auth_unknown_platform(self):
        loop = asyncio.new_event_loop()
        try:
            svc = AuthService.create_instance()
            result = loop.run_until_complete(svc.start_auth("unknown", "user1"))
            assert "未知平台" in result
        finally:
            loop.close()

    def test_handle_callback_success(self):
        loop = asyncio.new_event_loop()
        try:
            svc = AuthService.create_instance()
            svc.register("fanfou", MockAuthHandler())
            msg, user_id = loop.run_until_complete(
                svc.handle_callback("fanfou", {"oauth_token": "valid_token"})
            )
            assert msg == "授权成功"
            assert user_id == "user1"
        finally:
            loop.close()

    def test_handle_callback_failure(self):
        loop = asyncio.new_event_loop()
        try:
            svc = AuthService.create_instance()
            svc.register("fanfou", MockAuthHandler())
            msg, user_id = loop.run_until_complete(
                svc.handle_callback("fanfou", {"oauth_token": "bad"})
            )
            assert msg == "授权失败"
            assert user_id is None
        finally:
            loop.close()

    def test_remove_auth(self):
        loop = asyncio.new_event_loop()
        try:
            svc = AuthService.create_instance()
            handler = MockAuthHandler()
            svc.register("fanfou", handler)
            result = loop.run_until_complete(svc.remove_auth("fanfou", "user1"))
            assert result is True
            assert "user1" in handler.removed
        finally:
            loop.close()

    def test_remove_auth_unknown_platform(self):
        loop = asyncio.new_event_loop()
        try:
            svc = AuthService.create_instance()
            result = loop.run_until_complete(svc.remove_auth("unknown", "user1"))
            assert result is False
        finally:
            loop.close()
