"""
Unit tests for finbot/mcp/servers/finstripe/repositories.py

Covers uncovered branches in PaymentTransactionRepository:
- list_for_invoice (line 68)
- update_status happy path and not-found branch (lines 80-86)

Also covers isolation and pagination edge cases:
- list_for_vendor pagination (limit/offset)
- cross-vendor isolation
- get_by_transfer_id not found
- cross-namespace isolation

All tests use in-memory SQLite via the shared db fixture.
"""

import pytest
from datetime import date

from finbot.core.auth.session import session_manager
from finbot.core.data.models import Invoice
from finbot.core.data.repositories import VendorRepository
from finbot.mcp.servers.finstripe.repositories import PaymentTransactionRepository

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ============================================================================
# Helpers
# ============================================================================

def make_vendor(db, session, company_name="Test Vendor", email="vendor@test.com"):
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


def make_invoice(db, session, vendor_id, amount=1000.0):
    invoice = Invoice(
        namespace=session.namespace,
        vendor_id=vendor_id,
        description="Test invoice",
        amount=amount,
        status="approved",
        invoice_date=date.today(),
        due_date=date.today(),
        invoice_number="INV-001",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def make_repo(db, session):
    return PaymentTransactionRepository(db, session)


def create_txn(repo, vendor_id, invoice_id, transfer_id="TXN-001", amount=500.0):
    return repo.create_transaction(
        invoice_id=invoice_id,
        vendor_id=vendor_id,
        transfer_id=transfer_id,
        amount=amount,
        payment_method="ach",
    )


# ============================================================================
# list_for_invoice
# ============================================================================

class TestListForInvoice:

    def test_fs_repo_001_list_for_invoice_returns_matching_transactions(self, db):
        """
        FS-REPO-001

        Title: list_for_invoice returns transactions for the given invoice
        Basically question: Does list_for_invoice return only transactions tied to the specified invoice_id?

        Steps:
            1. Create two invoices and one transaction each.
            2. Call list_for_invoice with invoice_a's id.
        Expected Results:
            Only the transaction for invoice_a is returned.
        """
        session = session_manager.create_session(email="fs_repo_001@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice_a = make_invoice(db, session, vendor.id)
        invoice_b = make_invoice(db, session, vendor.id)

        create_txn(repo, vendor.id, invoice_a.id, transfer_id="TXN-A")
        create_txn(repo, vendor.id, invoice_b.id, transfer_id="TXN-B")

        results = repo.list_for_invoice(invoice_a.id)

        assert len(results) == 1
        assert results[0].transfer_id == "TXN-A"

    def test_fs_repo_002_list_for_invoice_returns_empty_when_no_transactions(self, db):
        """
        FS-REPO-002

        Title: list_for_invoice returns empty list when invoice has no transactions
        Basically question: Does list_for_invoice return an empty list for an invoice with no transactions?

        Steps:
            1. Create an invoice with no transactions.
            2. Call list_for_invoice with that invoice's id.
        Expected Results:
            Empty list returned.
        """
        session = session_manager.create_session(email="fs_repo_002@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice = make_invoice(db, session, vendor.id)

        results = repo.list_for_invoice(invoice.id)

        assert results == []

    def test_fs_repo_003_list_for_invoice_returns_multiple_transactions(self, db):
        """
        FS-REPO-003

        Title: list_for_invoice returns all transactions for an invoice with multiple payments
        Basically question: Does list_for_invoice return all transactions when an invoice has more than one?

        Steps:
            1. Create one invoice and two transactions against it.
            2. Call list_for_invoice.
        Expected Results:
            Both transactions are returned.
        """
        session = session_manager.create_session(email="fs_repo_003@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice = make_invoice(db, session, vendor.id)

        create_txn(repo, vendor.id, invoice.id, transfer_id="TXN-001")
        create_txn(repo, vendor.id, invoice.id, transfer_id="TXN-002")

        results = repo.list_for_invoice(invoice.id)

        assert len(results) == 2


# ============================================================================
# update_status
# ============================================================================

class TestUpdateStatus:

    def test_fs_repo_004_update_status_changes_status_and_returns_transaction(self, db):
        """
        FS-REPO-004

        Title: update_status updates the transaction status and returns the transaction
        Basically question: Does update_status correctly change the status field and return the updated transaction?

        Steps:
            1. Create a transaction with status="pending".
            2. Call update_status with status="completed".
        Expected Results:
            Returns the transaction with status="completed".
        """
        session = session_manager.create_session(email="fs_repo_004@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice = make_invoice(db, session, vendor.id)
        txn = create_txn(repo, vendor.id, invoice.id, transfer_id="TXN-UPD-001")

        result = repo.update_status("TXN-UPD-001", "completed")

        assert result is not None
        assert result.status == "completed"
        assert result.transfer_id == "TXN-UPD-001"

    def test_fs_repo_005_update_status_persists_to_db(self, db):
        """
        FS-REPO-005

        Title: update_status persists the new status to the database
        Basically question: Is the status change durable — does a re-fetch reflect the updated status?

        Steps:
            1. Create a transaction with status="pending".
            2. Call update_status with status="failed".
            3. Re-fetch the transaction via get_by_transfer_id.
        Expected Results:
            The re-fetched transaction has status="failed".
        """
        session = session_manager.create_session(email="fs_repo_005@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice = make_invoice(db, session, vendor.id)
        create_txn(repo, vendor.id, invoice.id, transfer_id="TXN-UPD-002")

        repo.update_status("TXN-UPD-002", "failed")
        fetched = repo.get_by_transfer_id("TXN-UPD-002")

        assert fetched.status == "failed"

    def test_fs_repo_006_update_status_returns_none_for_unknown_transfer_id(self, db):
        """
        FS-REPO-006

        Title: update_status returns None when transfer_id does not exist
        Basically question: Does update_status return None gracefully when no transaction matches the transfer_id?

        Steps:
            1. Call update_status with a transfer_id that does not exist.
        Expected Results:
            Returns None without raising.
        """
        session = session_manager.create_session(email="fs_repo_006@test.com")
        repo = make_repo(db, session)

        result = repo.update_status("NONEXISTENT-TXN", "completed")

        assert result is None


# ============================================================================
# get_by_transfer_id
# ============================================================================

class TestGetByTransferId:

    def test_fs_repo_007_get_by_transfer_id_returns_transaction(self, db):
        """
        FS-REPO-007

        Title: get_by_transfer_id returns the matching transaction
        Basically question: Does get_by_transfer_id return the correct transaction for a known transfer_id?

        Steps:
            1. Create a transaction with transfer_id="TXN-GET-001".
            2. Call get_by_transfer_id("TXN-GET-001").
        Expected Results:
            The transaction is returned with the correct transfer_id.
        """
        session = session_manager.create_session(email="fs_repo_007@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice = make_invoice(db, session, vendor.id)
        create_txn(repo, vendor.id, invoice.id, transfer_id="TXN-GET-001")

        result = repo.get_by_transfer_id("TXN-GET-001")

        assert result is not None
        assert result.transfer_id == "TXN-GET-001"

    def test_fs_repo_008_get_by_transfer_id_returns_none_when_not_found(self, db):
        """
        FS-REPO-008

        Title: get_by_transfer_id returns None for an unknown transfer_id
        Basically question: Does get_by_transfer_id return None gracefully when no match exists?

        Steps:
            1. Call get_by_transfer_id with a transfer_id that does not exist.
        Expected Results:
            Returns None.
        """
        session = session_manager.create_session(email="fs_repo_008@test.com")
        repo = make_repo(db, session)

        result = repo.get_by_transfer_id("DOES-NOT-EXIST")

        assert result is None


# ============================================================================
# list_for_vendor — pagination and isolation
# ============================================================================

class TestListForVendor:

    def test_fs_repo_009_list_for_vendor_respects_limit(self, db):
        """
        FS-REPO-009

        Title: list_for_vendor respects the limit parameter
        Basically question: Does list_for_vendor return at most limit transactions?

        Steps:
            1. Create 5 transactions for a vendor.
            2. Call list_for_vendor with limit=2.
        Expected Results:
            Exactly 2 transactions returned.
        """
        session = session_manager.create_session(email="fs_repo_009@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice = make_invoice(db, session, vendor.id)

        for i in range(5):
            create_txn(repo, vendor.id, invoice.id, transfer_id=f"TXN-LIM-{i:03d}")

        results = repo.list_for_vendor(vendor.id, limit=2)

        assert len(results) == 2

    def test_fs_repo_010_list_for_vendor_respects_offset(self, db):
        """
        FS-REPO-010

        Title: list_for_vendor respects the offset parameter
        Basically question: Does list_for_vendor skip transactions correctly when offset is set?

        Steps:
            1. Create 3 transactions for a vendor.
            2. Call list_for_vendor with offset=2.
        Expected Results:
            Exactly 1 transaction returned.
        """
        session = session_manager.create_session(email="fs_repo_010@test.com")
        vendor = make_vendor(db, session)
        repo = make_repo(db, session)
        invoice = make_invoice(db, session, vendor.id)

        for i in range(3):
            create_txn(repo, vendor.id, invoice.id, transfer_id=f"TXN-OFF-{i:03d}")

        results = repo.list_for_vendor(vendor.id, limit=50, offset=2)

        assert len(results) == 1

    def test_fs_repo_011_list_for_vendor_scoped_to_vendor_id(self, db):
        """
        FS-REPO-011

        Title: list_for_vendor does not return another vendor's transactions
        Basically question: Does list_for_vendor scope results strictly to the given vendor_id?

        Steps:
            1. Create two vendors, each with one transaction.
            2. Call list_for_vendor with vendor_a's id.
        Expected Results:
            Only vendor_a's transaction is returned.
        """
        session = session_manager.create_session(email="fs_repo_011@test.com")
        vendor_a = make_vendor(db, session, email="fs_a_011@test.com", company_name="Vendor A 011")
        vendor_b = make_vendor(db, session, email="fs_b_011@test.com", company_name="Vendor B 011")
        repo = make_repo(db, session)
        invoice_a = make_invoice(db, session, vendor_a.id)
        invoice_b = make_invoice(db, session, vendor_b.id)

        create_txn(repo, vendor_a.id, invoice_a.id, transfer_id="TXN-A-011")
        create_txn(repo, vendor_b.id, invoice_b.id, transfer_id="TXN-B-011")

        results = repo.list_for_vendor(vendor_a.id)

        assert len(results) == 1
        assert results[0].transfer_id == "TXN-A-011"

    def test_fs_repo_012_get_by_transfer_id_cross_namespace_returns_none(self, db):
        """
        FS-REPO-012

        Title: get_by_transfer_id returns None for a transaction in a different namespace
        Basically question: Does the namespace filter prevent cross-namespace transaction access?

        Steps:
            1. Create a transaction under namespace_a.
            2. Call get_by_transfer_id from a repo scoped to namespace_b.
        Expected Results:
            Returns None.
        """
        session_a = session_manager.create_session(email="fs_repo_012a@test.com")
        session_b = session_manager.create_session(email="fs_repo_012b@test.com")
        vendor = make_vendor(db, session_a)
        repo_a = make_repo(db, session_a)
        repo_b = make_repo(db, session_b)
        invoice = make_invoice(db, session_a, vendor.id)

        create_txn(repo_a, vendor.id, invoice.id, transfer_id="TXN-NS-012")

        result = repo_b.get_by_transfer_id("TXN-NS-012")

        assert result is None
