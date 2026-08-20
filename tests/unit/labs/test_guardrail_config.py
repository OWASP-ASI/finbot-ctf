"""Tests for Labs guardrail config: SSRF validation + repository CRUD."""

import socket
from unittest.mock import patch

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import (
    LabsGuardrailConfigRepository,
    validate_webhook_url,
    validate_webhook_url_async,
)


def _fake_addrinfo(*ip_strs: str):
    """Build a socket.getaddrinfo-shaped return value for the given IPs."""
    return [
        (2, 1, 6, "", (ip, 443)) if ":" not in ip else (10, 1, 6, "", (ip, 443, 0, 0))
        for ip in ip_strs
    ]


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

    def test_hostname_resolving_to_blocked_ip_is_rejected_in_production(self, monkeypatch):
        """DNS-based SSRF bypass: a hostname is not itself a literal IP, so
        the pre-fix check (ipaddress.ip_address(hostname)) would silently
        pass it through unchecked. It must still be blocked once it
        actually resolves to an internal address."""
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            return_value=_fake_addrinfo("127.0.0.1"),
        ):
            ok, err = validate_webhook_url("https://attacker-controlled.example/hook")
        assert ok is False
        assert "blocked" in err.lower()

    def test_hostname_resolving_to_metadata_ip_is_rejected_in_production(self, monkeypatch):
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            return_value=_fake_addrinfo("169.254.169.254"),
        ):
            ok, err = validate_webhook_url("https://looks-legit.example/hook")
        assert ok is False
        assert "blocked" in err.lower()

    def test_hostname_with_one_safe_and_one_unsafe_resolved_ip_is_rejected(self, monkeypatch):
        """If ANY resolved address is unsafe, reject -- an attacker (or a
        multi-homed/round-robin DNS setup) can control which address the
        actual outbound request happens to use."""
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            return_value=_fake_addrinfo("8.8.8.8", "127.0.0.1"),
        ):
            ok, err = validate_webhook_url("https://mixed.example/hook")
        assert ok is False

    def test_hostname_resolving_to_public_ip_is_allowed_in_production(self, monkeypatch):
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            return_value=_fake_addrinfo("8.8.8.8"),
        ):
            ok, err = validate_webhook_url("https://real-webhook-receiver.example/hook")
        assert ok is True
        assert err is None

    def test_unresolvable_hostname_is_rejected_in_production(self, monkeypatch):
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            side_effect=socket.gaierror("Name or service not known"),
        ):
            ok, err = validate_webhook_url("https://does-not-exist.invalid/hook")
        assert ok is False
        assert "resolve" in err.lower()

    def test_ipv4_mapped_ipv6_private_address_is_rejected_in_production(self, monkeypatch):
        """::ffff:10.0.0.5 is IPv4-mapped IPv6 -- must unwrap and check the
        underlying IPv4 address, not just the IPv6 shell."""
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            return_value=_fake_addrinfo("::ffff:10.0.0.5"),
        ):
            ok, err = validate_webhook_url("https://mapped.example/hook")
        assert ok is False

    def test_overlong_hostname_rejected_cleanly_in_production(self, monkeypatch):
        """socket.getaddrinfo raises UnicodeEncodeError (a UnicodeError
        subclass), not socket.gaierror, for a hostname whose label is too
        long for the idna codec -- confirmed directly against the real
        stdlib, not assumed. Must be rejected with a clean error, not an
        unhandled exception."""
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        ok, err = validate_webhook_url(f"https://{'x' * 300}.example/hook")
        assert ok is False
        assert "resolve" in err.lower()

    def test_hostname_resolution_not_triggered_in_debug_mode(self):
        """DEBUG mode's local-testing carve-out must still short-circuit
        before any DNS resolution happens -- no behavior change for the
        existing, intentional local-dev workflow."""
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo"
        ) as mock_getaddrinfo:
            ok, err = validate_webhook_url("https://anything.example/hook")
        assert ok is True
        mock_getaddrinfo.assert_not_called()


# =============================================================================
# Async wrapper -- offloads DNS resolution off the event loop, bounded by a
# timeout. See finbot/core/data/repositories.py:validate_webhook_url_async.
# =============================================================================


class TestValidateWebhookUrlAsync:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delegates_to_sync_validator_for_safe_url(self, monkeypatch):
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            return_value=_fake_addrinfo("8.8.8.8"),
        ):
            ok, err = await validate_webhook_url_async("https://real.example/hook")
        assert ok is True
        assert err is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delegates_to_sync_validator_for_unsafe_url(self, monkeypatch):
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        ok, err = await validate_webhook_url_async("https://127.0.0.1/hook")
        assert ok is False
        assert "blocked" in err.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_block_the_event_loop(self, monkeypatch):
        """The core DoS fix: a slow resolution must not block other
        concurrently-scheduled coroutines on the same event loop. Run a
        slow validation alongside a trivial coroutine and confirm the
        trivial one completes first -- proof the slow call actually ran on
        a separate thread rather than inline on the event loop."""
        import asyncio
        import time

        monkeypatch.setattr("finbot.config.settings.DEBUG", False)

        def _slow_getaddrinfo(*args, **kwargs):
            time.sleep(0.2)
            return _fake_addrinfo("8.8.8.8")

        order: list[str] = []

        async def _trivial():
            await asyncio.sleep(0)
            order.append("trivial")

        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            side_effect=_slow_getaddrinfo,
        ):
            async def _slow():
                await validate_webhook_url_async("https://slow.example/hook")
                order.append("slow")

            await asyncio.gather(_slow(), _trivial())

        assert order == ["trivial", "slow"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_times_out_on_slow_resolution(self, monkeypatch):
        import time

        monkeypatch.setattr("finbot.config.settings.DEBUG", False)

        def _hanging_getaddrinfo(*args, **kwargs):
            time.sleep(1.0)
            return _fake_addrinfo("8.8.8.8")

        with patch(
            "finbot.core.data.repositories.socket.getaddrinfo",
            side_effect=_hanging_getaddrinfo,
        ):
            ok, err = await validate_webhook_url_async(
                "https://hangs.example/hook", timeout=0.05
            )
        assert ok is False
        assert "timed out" in err.lower()


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

    def test_upsert_skip_url_validation_bypasses_the_check(self, monkeypatch):
        """skip_url_validation is for callers (the route handler) that
        already validated the URL themselves via the async, timeout-bounded
        pre-check -- re-running the sync check here would be a second,
        unbounded DNS resolution performed while holding an open DB
        session. Default (skip_url_validation=False) must still validate,
        confirmed by test_upsert_rejects_ssrf_url above."""
        monkeypatch.setattr("finbot.config.settings.DEBUG", False)
        config, created = self.repo.upsert(
            webhook_url="https://127.0.0.1/hook", skip_url_validation=True
        )
        assert created is True
        assert config.webhook_url == "https://127.0.0.1/hook"

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
