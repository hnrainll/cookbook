"""Tests for AuthService"""
from app.core.auth import AuthService


class MockAuthHandler:
    def __init__(self):
        self.auth_urls = {}
        self.removed = set()

    def gen_auth_url(self, user_id: str) -> str:
        url = f"https://example.com/auth?user={user_id}"
        self.auth_urls[user_id] = url
        return url

    def handle_callback(self, params: dict) -> tuple[str, str | None]:
        token = params.get("oauth_token")
        if token == "valid_token":
            return "授权成功", "user1"
        return "授权失败", None

    def remove_auth(self, user_id: str) -> bool:
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
        svc = AuthService.create_instance()
        handler = MockAuthHandler()
        svc.register("fanfou", handler)
        url = svc.start_auth("fanfou", "user1")
        assert "user1" in url

    def test_start_auth_unknown_platform(self):
        svc = AuthService.create_instance()
        result = svc.start_auth("unknown", "user1")
        assert "未知平台" in result

    def test_handle_callback_success(self):
        svc = AuthService.create_instance()
        svc.register("fanfou", MockAuthHandler())
        msg, user_id = svc.handle_callback("fanfou", {"oauth_token": "valid_token"})
        assert msg == "授权成功"
        assert user_id == "user1"

    def test_handle_callback_failure(self):
        svc = AuthService.create_instance()
        svc.register("fanfou", MockAuthHandler())
        msg, user_id = svc.handle_callback("fanfou", {"oauth_token": "bad"})
        assert msg == "授权失败"
        assert user_id is None

    def test_remove_auth(self):
        svc = AuthService.create_instance()
        handler = MockAuthHandler()
        svc.register("fanfou", handler)
        assert svc.remove_auth("fanfou", "user1") is True
        assert "user1" in handler.removed

    def test_remove_auth_unknown_platform(self):
        svc = AuthService.create_instance()
        assert svc.remove_auth("unknown", "user1") is False
