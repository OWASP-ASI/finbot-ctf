"""
Unit tests for finbot/mcp/servers/finmail/routing.py

Covers uncovered lines:
- get_department_addresses (line 40)
- route_and_deliver user branch — address matches a User in namespace (lines 149-165)

All tests use in-memory SQLite via the shared db fixture.
"""

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.models import User
from finbot.core.data.repositories import VendorRepository
from finbot.mcp.servers.finmail.repositories import EmailRepository
from finbot.mcp.servers.finmail.routing import (
    get_department_addresses,
    route_and_deliver,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ============================================================================
# Helpers
# ============================================================================

def make_repo(db, session):
    return EmailRepository(db, session)


def make_vendor(db, session, email="vendor@test.com", company_name="Test Vendor"):
    repo = VendorRepository(db, session)
    return repo.create_vendor(
        company_name=company_name,
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Alice",
        email=email,
        tin="12-3456789",
        bank_account_number="123456789012",
        bank_name="Test Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Alice",
    )


def make_user(db, namespace, email):
    user = User(
        user_id=email.replace("@", "_").replace(".", "_"),
        email=email,
        namespace=namespace,
        display_name="Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================================
# get_department_addresses
# ============================================================================

class TestGetDepartmentAddresses:

    def test_fm_rte_001_get_department_addresses_returns_all_departments(self):
        """
        FM-RTE-001

        Title: get_department_addresses returns a mapping of all department addresses
        Basically question: Does get_department_addresses return a dict with namespace-scoped addresses for all departments?

        Steps:
            1. Call get_department_addresses("acme").
        Expected Results:
            Dict contains keys like "admin@acme.finbot", "finance@acme.finbot", etc.
            Each value is a non-empty description string.
        """
        result = get_department_addresses("acme")

        assert isinstance(result, dict)
        assert len(result) > 0
        assert "admin@acme.finbot" in result
        assert "finance@acme.finbot" in result
        assert all(isinstance(v, str) and v for v in result.values())

    def test_fm_rte_002_get_department_addresses_scoped_to_namespace(self):
        """
        FM-RTE-002

        Title: get_department_addresses scopes addresses to the given namespace
        Basically question: Do all addresses returned by get_department_addresses end with @{namespace}.finbot?

        Steps:
            1. Call get_department_addresses("testcorp").
        Expected Results:
            All keys end with "@testcorp.finbot".
        """
        result = get_department_addresses("testcorp")

        assert all(k.endswith("@testcorp.finbot") for k in result)


# ============================================================================
# route_and_deliver — user branch
# ============================================================================

class TestRouteAndDeliverUserBranch:

    def test_fm_rte_003_delivery_to_user_address_routes_to_admin_inbox(self, db):
        """
        FM-RTE-003

        Title: route_and_deliver routes a User's email address to the admin inbox
        Basically question: Does route_and_deliver create an admin inbox email when the recipient is a registered User?

        Steps:
            1. Create a User with a known email in the namespace.
            2. Call route_and_deliver with that email address as the to recipient.
        Expected Results:
            Delivery type is "admin" and an admin email is created in the repo.
        """
        session = session_manager.create_session(email="fm_rte_003@test.com")
        repo = make_repo(db, session)
        namespace = session.namespace

        user_email = f"user_rte_003@{namespace}.example.com"
        make_user(db, namespace, user_email)

        result = route_and_deliver(
            db=db,
            repo=repo,
            namespace=namespace,
            to=[user_email],
            subject="Hello User",
            body="Body text",
        )

        assert result["sent"] is True
        assert len(result["deliveries"]) == 1
        assert result["deliveries"][0]["type"] == "admin"
        assert result["deliveries"][0]["email"] == user_email

        admin_emails = repo.list_admin_emails()
        assert any(e.subject == "Hello User" for e in admin_emails)

    def test_fm_rte_004_delivery_to_unknown_address_routes_to_external_inbox(self, db):
        """
        FM-RTE-004

        Title: route_and_deliver routes an unknown address to the external dead-drop inbox
        Basically question: Does route_and_deliver store unresolvable addresses in the external inbox?

        Steps:
            1. Call route_and_deliver with a completely unknown address.
        Expected Results:
            Delivery type is "external" and an external email is created in the repo.
        """
        session = session_manager.create_session(email="fm_rte_004@test.com")
        repo = make_repo(db, session)
        namespace = session.namespace

        result = route_and_deliver(
            db=db,
            repo=repo,
            namespace=namespace,
            to=["nobody@outsider.com"],
            subject="External msg",
            body="Body",
        )

        assert result["sent"] is True
        assert result["deliveries"][0]["type"] == "external"

        external_emails = repo.list_external_emails()
        assert any(e.subject == "External msg" for e in external_emails)
