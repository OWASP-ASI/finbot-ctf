"""Tests for Labs guardrail config: SSRF validation + repository CRUD."""

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import (
    LabsGuardrailConfigRepository,
    validate_webhook_url,
)


# =============================================================================
# SSRF validation
# =============================================================================


class TestValidateWebhookUrl:
    """validate_webhook_url blocks private/internal addresses."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/webhook",
            "https://hooks.example.com:8443/guardrail",
            "http://myserver.com:8080/hook",
            "https://guardrail.ngrok.io/v1",
        ],
    )
    def test_valid_urls(self, url):
        ok, err = validate_webhook_url(url)
        assert ok is True
        assert err is None

    @pytest.mark.parametrize(
        "url,expected_fragment",
        [
            ("", "required"),
            ("ftp://example.com/hook", "scheme"),
            ("https://", "hostname"),
            ("https://metadata.google.internal/v1", "not allowed"),
            ("https://example.com:22/hook", "not in the allowed range"),
        ],
    )
    def test_always_blocked_urls(self, url, expected_fragment):
        ok, err = validate_webhook_url(url)
        assert ok is False
        assert expected_fragment.lower() in err.lower()

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:5000/hook",
            "http://127.0.0.1:8080/hook",
            "http://10.0.0.5:3000/hook",
            "http://192.168.1.1:9000/hook",
        ],
    )
    def test_local_urls_allowed_in_debug(self, url):
        """In DEBUG mode (default for tests), local endpoints are allowed."""
        ok, err = validate_webhook_url(url)
        assert ok is True, f"Expected allowed in debug mode, got: {err}"

    @pytest.mark.parametrize(
        "url,expected_fragment",
        [
            ("https://localhost/hook", "not allowed"),
            ("https://127.0.0.1/hook", "blocked range"),
            ("https://10.0.0.5/hook", "blocked range"),
            ("https://172.16.0.1/hook", "blocked range"),
            ("https://192.168.1.1/hook", "blocked range"),
            ("https://169.254.169.254/latest/meta-data/", "blocked range"),
            ("https://[::1]/hook", "blocked range"),
        ],
    )
    def test_private_urls_blocked_in_production(self, url, expected_fragment, monkeypatch):
        """In production (DEBUG=False), private IPs and localhost are blocked."""
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        ok, err = validate_webhook_url(url)
        assert ok is False
        assert expected_fragment.lower() in err.lower()


# =============================================================================
# Repository CRUD
# =============================================================================


class TestLabsGuardrailConfigRepository:
    """CRUD operations on LabsGuardrailConfig."""

    @pytest.fixture(autouse=True)
    def _setup(self, db):
        self.db = db
        self.session = session_manager.create_session(email="labs_test@example.com")
        self.repo = LabsGuardrailConfigRepository(db, self.session)

    def test_upsert_creates_config(self):
        config, created = self.repo.upsert(
            webhook_url="https://example.com/hook",
        )
        assert created is True
        assert config.webhook_url == "https://example.com/hook"
        assert config.enabled is True
        assert config.timeout_seconds == 5
        assert config.signing_secret  # auto-generated
        assert config.namespace == self.session.namespace

    def test_upsert_updates_existing(self):
        config1, created1 = self.repo.upsert(
            webhook_url="https://example.com/hook",
        )
        assert created1 is True
        original_secret = config1.signing_secret

        config2, created2 = self.repo.upsert(
            webhook_url="https://other.example.com/hook",
            timeout_seconds=10,
        )
        assert created2 is False
        assert config2.id == config1.id
        assert config2.webhook_url == "https://other.example.com/hook"
        assert config2.timeout_seconds == 10
        assert config2.signing_secret == original_secret

    def test_upsert_rejects_ssrf_url(self, monkeypatch):
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with pytest.raises(ValueError, match="blocked range"):
            self.repo.upsert(webhook_url="https://127.0.0.1/hook")

    def test_upsert_rejects_unknown_hook_kinds(self):
        with pytest.raises(ValueError, match="Unknown hook kinds"):
            self.repo.upsert(
                webhook_url="https://example.com/hook",
                hooks={"before_model": True, "invalid_hook": True},
            )

    def test_upsert_clamps_timeout(self):
        config, _ = self.repo.upsert(
            webhook_url="https://example.com/hook",
            timeout_seconds=999,
        )
        assert config.timeout_seconds == 30

        config2, _ = self.repo.upsert(
            webhook_url="https://example.com/hook",
            timeout_seconds=0,
        )
        assert config2.timeout_seconds == 1

    def test_get_for_current_user(self):
        assert self.repo.get_for_current_user() is None

        self.repo.upsert(webhook_url="https://example.com/hook")
        config = self.repo.get_for_current_user()
        assert config is not None
        assert config.user_id == self.session.user_id

    def test_toggle_enabled(self):
        self.repo.upsert(webhook_url="https://example.com/hook")
        config = self.repo.toggle_enabled()
        assert config.enabled is False

        config = self.repo.toggle_enabled()
        assert config.enabled is True

    def test_toggle_enabled_no_config(self):
        assert self.repo.toggle_enabled() is None

    def test_rotate_secret(self):
        self.repo.upsert(webhook_url="https://example.com/hook")
        original = self.repo.get_for_current_user().signing_secret

        config = self.repo.rotate_secret()
        assert config.signing_secret != original
        assert len(config.signing_secret) > 20

    def test_rotate_secret_no_config(self):
        assert self.repo.rotate_secret() is None

    def test_delete_config(self):
        self.repo.upsert(webhook_url="https://example.com/hook")
        assert self.repo.delete_config() is True
        assert self.repo.get_for_current_user() is None

    def test_delete_config_no_config(self):
        assert self.repo.delete_config() is False

    def test_hooks_default_all_enabled(self):
        config, _ = self.repo.upsert(webhook_url="https://example.com/hook")
        hooks = config.get_hooks()
        assert hooks == {
            "before_model": True,
            "after_model": True,
            "before_tool": True,
            "after_tool": True,
        }

    def test_custom_hooks(self):
        config, _ = self.repo.upsert(
            webhook_url="https://example.com/hook",
            hooks={"before_tool": True, "after_tool": False},
        )
        hooks = config.get_hooks()
        assert hooks["before_tool"] is True
        assert hooks["after_tool"] is False

    def test_to_dict_excludes_secret(self):
        self.repo.upsert(webhook_url="https://example.com/hook")
        config = self.repo.get_for_current_user()
        d = config.to_dict()
        assert "signing_secret" not in d
        assert d["webhook_url"] == "https://example.com/hook"
        assert isinstance(d["hooks"], dict)

    def test_namespace_isolation(self):
        """Config for one user is not visible to another."""
        other_session = session_manager.create_session(email="other@example.com")
        other_repo = LabsGuardrailConfigRepository(self.db, other_session)

        self.repo.upsert(webhook_url="https://example.com/hook")
        assert other_repo.get_for_current_user() is None
