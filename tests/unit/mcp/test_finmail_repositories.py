"""
Unit tests for finbot/mcp/servers/finmail/repositories.py

Covers the uncovered branches in EmailRepository:
- list_vendor_emails with message_type and is_read filters
- get_vendor_email_stats
- get_vendor_unread_count
- mark_all_vendor_as_read
- list_admin_emails with message_type filter
- get_admin_email_stats
- mark_all_admin_as_read
- list_external_emails
- get_external_email_stats
- mark_as_read when already read

All tests use in-memory SQLite via the shared db fixture.
"""

import pytest
from contextlib import contextmanager

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import VendorRepository
from finbot.mcp.servers.finmail.repositories import EmailRepository

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ============================================================================
# Helpers
# ============================================================================

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


def make_repo(db, session):
    return EmailRepository(db, session)


def create_vendor_email(repo, vendor_id, message_type="notification", subject="Test", is_read=False):
    msg = repo.create_email(
        inbox_type="vendor",
        subject=subject,
        body="Test body",
        message_type=message_type,
        sender_name="Agent",
        vendor_id=vendor_id,
    )
    if is_read:
        repo.mark_as_read(msg.id)
    return msg


def create_admin_email(repo, message_type="notification", subject="Test"):
    return repo.create_email(
        inbox_type="admin",
        subject=subject,
        body="Admin body",
        message_type=message_type,
        sender_name="Agent",
    )


def create_external_email(repo, subject="External"):
    return repo.create_email(
        inbox_type="external",
        subject=subject,
        body="External body",
        message_type="inbound",
        sender_name="Unknown",
    )


# ============================================================================
# list_vendor_emails — filter branches
# ============================================================================

class TestListVendorEmailsFilters:

    def test_fm_repo_001_list_vendor_emails_filter_by_message_type(self, db):
        """
        FM-REPO-001

        Title: list_vendor_emails filters correctly by message_type
        Basically question: Does list_vendor_emails return only emails matching the given message_type?

        Steps:
            1. Create two vendor emails with different message types.
            2. Call list_vendor_emails with message_type="invoice".
        Expected Results:
            Only the invoice-type email is returned.
        """
        session = session_manager.create_session(email="repo_001@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id, message_type="notification")
        create_vendor_email(repo, vendor.id, message_type="invoice")

        results = repo.list_vendor_emails(vendor.id, message_type="invoice")

        assert len(results) == 1
        assert results[0].message_type == "invoice"

    def test_fm_repo_002_list_vendor_emails_filter_by_is_read_false(self, db):
        """
        FM-REPO-002

        Title: list_vendor_emails filters to unread emails only
        Basically question: Does list_vendor_emails return only unread emails when is_read=False?

        Steps:
            1. Create one read and one unread vendor email.
            2. Call list_vendor_emails with is_read=False.
        Expected Results:
            Only the unread email is returned.
        """
        session = session_manager.create_session(email="repo_002@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id, subject="Unread")
        create_vendor_email(repo, vendor.id, subject="Read", is_read=True)

        results = repo.list_vendor_emails(vendor.id, is_read=False)

        assert len(results) == 1
        assert results[0].subject == "Unread"

    def test_fm_repo_003_list_vendor_emails_filter_by_is_read_true(self, db):
        """
        FM-REPO-003

        Title: list_vendor_emails filters to read emails only
        Basically question: Does list_vendor_emails return only read emails when is_read=True?

        Steps:
            1. Create one read and one unread vendor email.
            2. Call list_vendor_emails with is_read=True.
        Expected Results:
            Only the read email is returned.
        """
        session = session_manager.create_session(email="repo_003@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id, subject="Unread")
        create_vendor_email(repo, vendor.id, subject="Read", is_read=True)

        results = repo.list_vendor_emails(vendor.id, is_read=True)

        assert len(results) == 1
        assert results[0].subject == "Read"


# ============================================================================
# get_vendor_email_stats
# ============================================================================

class TestGetVendorEmailStats:

    def test_fm_repo_004_get_vendor_email_stats_empty(self, db):
        """
        FM-REPO-004

        Title: get_vendor_email_stats returns zeros for vendor with no emails
        Basically question: Does get_vendor_email_stats return total=0 and unread=0 when no emails exist?

        Steps:
            1. Create a vendor with no emails.
            2. Call get_vendor_email_stats.
        Expected Results:
            total=0, unread=0, by_type={}.
        """
        session = session_manager.create_session(email="repo_004@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        stats = repo.get_vendor_email_stats(vendor.id)

        assert stats["total"] == 0
        assert stats["unread"] == 0
        assert stats["by_type"] == {}

    def test_fm_repo_005_get_vendor_email_stats_with_emails(self, db):
        """
        FM-REPO-005

        Title: get_vendor_email_stats returns correct counts with mixed emails
        Basically question: Does get_vendor_email_stats correctly count total, unread, and by_type?

        Steps:
            1. Create 2 unread notification emails and 1 read invoice email.
            2. Call get_vendor_email_stats.
        Expected Results:
            total=3, unread=2, by_type has correct counts per type.
        """
        session = session_manager.create_session(email="repo_005@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id, message_type="notification")
        create_vendor_email(repo, vendor.id, message_type="notification")
        create_vendor_email(repo, vendor.id, message_type="invoice", is_read=True)

        stats = repo.get_vendor_email_stats(vendor.id)

        assert stats["total"] == 3
        assert stats["unread"] == 2
        assert stats["by_type"]["notification"] == 2
        assert stats["by_type"]["invoice"] == 1


# ============================================================================
# get_vendor_unread_count
# ============================================================================

class TestGetVendorUnreadCount:

    def test_fm_repo_006_get_vendor_unread_count(self, db):
        """
        FM-REPO-006

        Title: get_vendor_unread_count returns correct unread count
        Basically question: Does get_vendor_unread_count return the number of unread vendor emails?

        Steps:
            1. Create 2 unread and 1 read vendor emails.
            2. Call get_vendor_unread_count.
        Expected Results:
            Returns 2.
        """
        session = session_manager.create_session(email="repo_006@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id)
        create_vendor_email(repo, vendor.id)
        create_vendor_email(repo, vendor.id, is_read=True)

        count = repo.get_vendor_unread_count(vendor.id)

        assert count == 2

    def test_fm_repo_007_get_vendor_unread_count_zero(self, db):
        """
        FM-REPO-007

        Title: get_vendor_unread_count returns 0 when all emails are read
        Basically question: Does get_vendor_unread_count return 0 when no unread emails exist?

        Steps:
            1. Create 2 read vendor emails.
            2. Call get_vendor_unread_count.
        Expected Results:
            Returns 0.
        """
        session = session_manager.create_session(email="repo_007@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id, is_read=True)
        create_vendor_email(repo, vendor.id, is_read=True)

        count = repo.get_vendor_unread_count(vendor.id)

        assert count == 0


# ============================================================================
# mark_all_vendor_as_read
# ============================================================================

class TestMarkAllVendorAsRead:

    def test_fm_repo_008_mark_all_vendor_as_read(self, db):
        """
        FM-REPO-008

        Title: mark_all_vendor_as_read marks all unread vendor emails as read
        Basically question: Does mark_all_vendor_as_read update all unread vendor emails and return the count?

        Steps:
            1. Create 3 unread vendor emails.
            2. Call mark_all_vendor_as_read.
        Expected Results:
            Returns 3, all emails are now read.
        """
        session = session_manager.create_session(email="repo_008@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id)
        create_vendor_email(repo, vendor.id)
        create_vendor_email(repo, vendor.id)

        count = repo.mark_all_vendor_as_read(vendor.id)

        assert count == 3
        assert repo.get_vendor_unread_count(vendor.id) == 0

    def test_fm_repo_009_mark_all_vendor_as_read_skips_already_read(self, db):
        """
        FM-REPO-009

        Title: mark_all_vendor_as_read only updates unread emails
        Basically question: Does mark_all_vendor_as_read return 0 when all emails are already read?

        Steps:
            1. Create 2 already-read vendor emails.
            2. Call mark_all_vendor_as_read.
        Expected Results:
            Returns 0.
        """
        session = session_manager.create_session(email="repo_009@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor.id, is_read=True)
        create_vendor_email(repo, vendor.id, is_read=True)

        count = repo.mark_all_vendor_as_read(vendor.id)

        assert count == 0


# ============================================================================
# list_admin_emails — filter branch
# ============================================================================

class TestListAdminEmailsFilters:

    def test_fm_repo_010_list_admin_emails_filter_by_message_type(self, db):
        """
        FM-REPO-010

        Title: list_admin_emails filters correctly by message_type
        Basically question: Does list_admin_emails return only emails matching the given message_type?

        Steps:
            1. Create two admin emails with different message types.
            2. Call list_admin_emails with message_type="alert".
        Expected Results:
            Only the alert-type email is returned.
        """
        session = session_manager.create_session(email="repo_010@test.com")
        repo = make_repo(db, session)

        create_admin_email(repo, message_type="notification")
        create_admin_email(repo, message_type="alert")

        results = repo.list_admin_emails(message_type="alert")

        assert len(results) == 1
        assert results[0].message_type == "alert"

    def test_fm_repo_011_list_admin_emails_filter_by_is_read(self, db):
        """
        FM-REPO-011

        Title: list_admin_emails filters to unread emails when is_read=False
        Basically question: Does list_admin_emails return only unread admin emails when is_read=False?

        Steps:
            1. Create one read and one unread admin email.
            2. Call list_admin_emails with is_read=False.
        Expected Results:
            Only the unread email is returned.
        """
        session = session_manager.create_session(email="repo_011@test.com")
        repo = make_repo(db, session)

        unread = create_admin_email(repo, subject="Unread")
        read = create_admin_email(repo, subject="Read")
        repo.mark_as_read(read.id)

        results = repo.list_admin_emails(is_read=False)

        assert len(results) == 1
        assert results[0].subject == "Unread"


# ============================================================================
# get_admin_email_stats
# ============================================================================

class TestGetAdminEmailStats:

    def test_fm_repo_012_get_admin_email_stats_empty(self, db):
        """
        FM-REPO-012

        Title: get_admin_email_stats returns zeros when no admin emails exist
        Basically question: Does get_admin_email_stats return total=0 and unread=0 when inbox is empty?

        Steps:
            1. Create a fresh namespace with no admin emails.
            2. Call get_admin_email_stats.
        Expected Results:
            total=0, unread=0, by_type={}.
        """
        session = session_manager.create_session(email="repo_012@test.com")
        repo = make_repo(db, session)

        stats = repo.get_admin_email_stats()

        assert stats["total"] == 0
        assert stats["unread"] == 0
        assert stats["by_type"] == {}

    def test_fm_repo_013_get_admin_email_stats_with_emails(self, db):
        """
        FM-REPO-013

        Title: get_admin_email_stats returns correct counts with mixed admin emails
        Basically question: Does get_admin_email_stats correctly count total, unread, and by_type?

        Steps:
            1. Create 2 unread notification emails and 1 read alert email.
            2. Call get_admin_email_stats.
        Expected Results:
            total=3, unread=2, by_type has correct counts.
        """
        session = session_manager.create_session(email="repo_013@test.com")
        repo = make_repo(db, session)

        create_admin_email(repo, message_type="notification")
        create_admin_email(repo, message_type="notification")
        read = create_admin_email(repo, message_type="alert")
        repo.mark_as_read(read.id)

        stats = repo.get_admin_email_stats()

        assert stats["total"] == 3
        assert stats["unread"] == 2
        assert stats["by_type"]["notification"] == 2
        assert stats["by_type"]["alert"] == 1


# ============================================================================
# mark_all_admin_as_read
# ============================================================================

class TestMarkAllAdminAsRead:

    def test_fm_repo_014_mark_all_admin_as_read(self, db):
        """
        FM-REPO-014

        Title: mark_all_admin_as_read marks all unread admin emails as read
        Basically question: Does mark_all_admin_as_read update all unread admin emails and return the count?

        Steps:
            1. Create 3 unread admin emails.
            2. Call mark_all_admin_as_read.
        Expected Results:
            Returns 3, all emails now read.
        """
        session = session_manager.create_session(email="repo_014@test.com")
        repo = make_repo(db, session)

        create_admin_email(repo)
        create_admin_email(repo)
        create_admin_email(repo)

        count = repo.mark_all_admin_as_read()

        assert count == 3
        stats = repo.get_admin_email_stats()
        assert stats["unread"] == 0

    def test_fm_repo_015_mark_all_admin_as_read_returns_zero_when_none_unread(self, db):
        """
        FM-REPO-015

        Title: mark_all_admin_as_read returns 0 when all admin emails are already read
        Basically question: Does mark_all_admin_as_read return 0 when there are no unread admin emails?

        Steps:
            1. Create 2 admin emails and mark them read.
            2. Call mark_all_admin_as_read.
        Expected Results:
            Returns 0.
        """
        session = session_manager.create_session(email="repo_015@test.com")
        repo = make_repo(db, session)

        e1 = create_admin_email(repo)
        e2 = create_admin_email(repo)
        repo.mark_as_read(e1.id)
        repo.mark_as_read(e2.id)

        count = repo.mark_all_admin_as_read()

        assert count == 0


# ============================================================================
# list_external_emails / get_external_email_stats
# ============================================================================

class TestExternalEmails:

    def test_fm_repo_016_list_external_emails(self, db):
        """
        FM-REPO-016

        Title: list_external_emails returns external inbox emails
        Basically question: Does list_external_emails return emails with inbox_type=external?

        Steps:
            1. Create 2 external emails and 1 admin email.
            2. Call list_external_emails.
        Expected Results:
            Returns only the 2 external emails.
        """
        session = session_manager.create_session(email="repo_016@test.com")
        repo = make_repo(db, session)

        create_external_email(repo, subject="Ext 1")
        create_external_email(repo, subject="Ext 2")
        create_admin_email(repo)

        results = repo.list_external_emails()

        assert len(results) == 2
        assert all(e.inbox_type == "external" for e in results)

    def test_fm_repo_017_get_external_email_stats(self, db):
        """
        FM-REPO-017

        Title: get_external_email_stats returns total and unread for external inbox
        Basically question: Does get_external_email_stats correctly count external emails?

        Steps:
            1. Create 2 external emails (both unread by default).
            2. Call get_external_email_stats.
        Expected Results:
            total=2, unread=2.
        """
        session = session_manager.create_session(email="repo_017@test.com")
        repo = make_repo(db, session)

        create_external_email(repo)
        create_external_email(repo)

        stats = repo.get_external_email_stats()

        assert stats["total"] == 2
        assert stats["unread"] == 2

    def test_fm_repo_018_get_external_email_stats_empty(self, db):
        """
        FM-REPO-018

        Title: get_external_email_stats returns zeros when no external emails exist
        Basically question: Does get_external_email_stats return total=0 when external inbox is empty?

        Steps:
            1. No external emails created.
            2. Call get_external_email_stats.
        Expected Results:
            total=0, unread=0.
        """
        session = session_manager.create_session(email="repo_018@test.com")
        repo = make_repo(db, session)

        stats = repo.get_external_email_stats()

        assert stats["total"] == 0
        assert stats["unread"] == 0


# ============================================================================
# mark_as_read — already read branch
# ============================================================================

class TestMarkAsRead:

    def test_fm_repo_019_mark_as_read_already_read_returns_email(self, db):
        """
        FM-REPO-019

        Title: mark_as_read returns email unchanged when already marked read
        Basically question: Does mark_as_read return the email without modifying it when it is already read?

        Steps:
            1. Create and mark an email as read.
            2. Call mark_as_read again on the same email.
        Expected Results:
            Returns the email, is_read remains True, no error raised.
        """
        session = session_manager.create_session(email="repo_019@test.com")
        repo = make_repo(db, session)

        email = create_admin_email(repo)
        repo.mark_as_read(email.id)

        result = repo.mark_as_read(email.id)

        assert result is not None
        assert result.is_read is True

    def test_fm_repo_020_mark_as_read_nonexistent_returns_none(self, db):
        """
        FM-REPO-020

        Title: mark_as_read returns None for a non-existent email ID
        Basically question: Does mark_as_read return None gracefully when the email does not exist?

        Steps:
            1. Call mark_as_read with email_id=99999.
        Expected Results:
            Returns None without raising.
        """
        session = session_manager.create_session(email="repo_020@test.com")
        repo = make_repo(db, session)

        result = repo.mark_as_read(99999)

        assert result is None


# ============================================================================
# list_admin_emails — is_read=True filter
# ============================================================================

class TestListAdminEmailsIsReadTrue:

    def test_fm_repo_021_list_admin_emails_filter_by_is_read_true(self, db):
        """
        FM-REPO-021

        Title: list_admin_emails filters to read emails when is_read=True
        Basically question: Does list_admin_emails return only read admin emails when is_read=True?

        Steps:
            1. Create one read and one unread admin email.
            2. Call list_admin_emails with is_read=True.
        Expected Results:
            Only the read email is returned.
        """
        session = session_manager.create_session(email="repo_021@test.com")
        repo = make_repo(db, session)

        unread = create_admin_email(repo, subject="Unread")
        read = create_admin_email(repo, subject="Read")
        repo.mark_as_read(read.id)

        results = repo.list_admin_emails(is_read=True)

        assert len(results) == 1
        assert results[0].subject == "Read"


# ============================================================================
# Pagination — limit and offset
# ============================================================================

class TestPagination:

    def test_fm_repo_022_list_vendor_emails_limit(self, db):
        """
        FM-REPO-022

        Title: list_vendor_emails respects the limit parameter
        Basically question: Does list_vendor_emails return at most limit emails?

        Steps:
            1. Create 5 vendor emails.
            2. Call list_vendor_emails with limit=2.
        Expected Results:
            Exactly 2 emails are returned.
        """
        session = session_manager.create_session(email="repo_022@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        for i in range(5):
            create_vendor_email(repo, vendor.id, subject=f"Email {i}")

        results = repo.list_vendor_emails(vendor.id, limit=2)

        assert len(results) == 2

    def test_fm_repo_023_list_vendor_emails_offset(self, db):
        """
        FM-REPO-023

        Title: list_vendor_emails respects the offset parameter
        Basically question: Does list_vendor_emails skip emails correctly when offset is set?

        Steps:
            1. Create 3 vendor emails.
            2. Call list_vendor_emails with limit=50 and offset=2.
        Expected Results:
            Only 1 email is returned (the third one).
        """
        session = session_manager.create_session(email="repo_023@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)

        for i in range(3):
            create_vendor_email(repo, vendor.id, subject=f"Email {i}")

        results = repo.list_vendor_emails(vendor.id, limit=50, offset=2)

        assert len(results) == 1


# ============================================================================
# Cross-vendor isolation
# ============================================================================

class TestCrossVendorIsolation:

    def test_fm_repo_024_list_vendor_emails_scoped_to_vendor_id(self, db):
        """
        FM-REPO-024

        Title: list_vendor_emails does not return another vendor's emails
        Basically question: Does list_vendor_emails scope results strictly to the given vendor_id?

        Steps:
            1. Create two vendors, each with one email.
            2. Call list_vendor_emails with vendor_a's id.
        Expected Results:
            Only vendor_a's email is returned; vendor_b's is not.
        """
        session = session_manager.create_session(email="repo_024@test.com")
        vendor_a = make_vendor(db, session, email="vendor_a_024@test.com", company_name="Vendor A 024")
        vendor_b = make_vendor(db, session, email="vendor_b_024@test.com", company_name="Vendor B 024")
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor_a.id, subject="A email")
        create_vendor_email(repo, vendor_b.id, subject="B email")

        results = repo.list_vendor_emails(vendor_a.id)

        assert len(results) == 1
        assert results[0].subject == "A email"

    def test_fm_repo_025_mark_all_vendor_as_read_does_not_affect_other_vendor(self, db):
        """
        FM-REPO-025

        Title: mark_all_vendor_as_read only marks the specified vendor's emails
        Basically question: Does mark_all_vendor_as_read leave another vendor's emails unread?

        Steps:
            1. Create two vendors, each with one unread email.
            2. Call mark_all_vendor_as_read for vendor_a.
        Expected Results:
            vendor_a's email is read; vendor_b's email remains unread.
        """
        session = session_manager.create_session(email="repo_025@test.com")
        vendor_a = make_vendor(db, session, email="vendor_a_025@test.com", company_name="Vendor A 025")
        vendor_b = make_vendor(db, session, email="vendor_b_025@test.com", company_name="Vendor B 025")
        repo = make_repo(db, session)

        create_vendor_email(repo, vendor_a.id)
        create_vendor_email(repo, vendor_b.id)

        repo.mark_all_vendor_as_read(vendor_a.id)

        assert repo.get_vendor_unread_count(vendor_a.id) == 0
        assert repo.get_vendor_unread_count(vendor_b.id) == 1

    def test_fm_repo_026_get_email_cross_namespace_returns_none(self, db):
        """
        FM-REPO-026

        Title: get_email returns None for an email belonging to a different namespace
        Basically question: Does the namespace filter prevent cross-namespace email access via get_email?

        Steps:
            1. Create an email under namespace_a.
            2. Create a repo for namespace_b.
            3. Call get_email with namespace_a's email ID from namespace_b's repo.
        Expected Results:
            Returns None — the email is not accessible across namespaces.
        """
        session_a = session_manager.create_session(email="repo_026a@test.com")
        session_b = session_manager.create_session(email="repo_026b@test.com")
        repo_a = make_repo(db, session_a)
        repo_b = make_repo(db, session_b)

        email = create_admin_email(repo_a, subject="Secret")

        result = repo_b.get_email(email.id)

        assert result is None


# ============================================================================
# Email model methods
# ============================================================================

class TestEmailModel:

    def test_fm_repo_027_repr(self, db):
        """
        FM-REPO-027

        Title: Email __repr__ returns expected string
        Basically question: Does Email.__repr__ include the id, inbox_type, and message_type?

        Steps:
            1. Create an admin email.
            2. Call repr() on it.
        Expected Results:
            String contains the email id, inbox_type, and message_type.
        """
        session = session_manager.create_session(email="repo_027@test.com")
        repo = make_repo(db, session)
        email = create_admin_email(repo, message_type="notification")

        r = repr(email)

        assert str(email.id) in r
        assert "admin" in r

    def test_fm_repo_028_parse_addresses_returns_none_for_invalid_json(self, db):
        """
        FM-REPO-028

        Title: _parse_addresses returns None for invalid JSON
        Basically question: Does _parse_addresses return None gracefully when the stored value is not valid JSON?

        Steps:
            1. Create an email.
            2. Manually set to_addresses to an invalid JSON string.
            3. Call to_dict() which internally calls _parse_addresses.
        Expected Results:
            to_addresses in the dict is None (no exception raised).
        """
        session = session_manager.create_session(email="repo_028@test.com")
        repo = make_repo(db, session)
        email = create_admin_email(repo)
        email.to_addresses = "not valid json {{{"

        result = email.to_dict()

        assert result["to_addresses"] is None

    def test_fm_repo_029_to_summary_dict_truncates_long_body(self, db):
        """
        FM-REPO-029

        Title: to_summary_dict truncates body_preview when body exceeds preview_length
        Basically question: Does to_summary_dict append "..." when body is longer than preview_length?

        Steps:
            1. Create an email with a body longer than 150 characters.
            2. Call to_summary_dict() with default preview_length.
        Expected Results:
            body_preview ends with "..." and is at most preview_length + 3 chars long.
        """
        session = session_manager.create_session(email="repo_029@test.com")
        repo = make_repo(db, session)
        long_body = "A" * 200
        email = repo.create_email(
            inbox_type="admin",
            subject="Long body",
            body=long_body,
            message_type="notification",
            sender_name="Agent",
        )

        result = email.to_summary_dict()

        assert result["body_preview"].endswith("...")
        assert len(result["body_preview"]) == 153  # 150 + len("...")
