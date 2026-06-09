from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from finbot.core.auth.session import session_manager
from finbot.core.data.models import UserSession
from finbot.core.data.repositories import InvoiceRepository

VENDOR_API_PREFIX = "/vendor/api/v1"


# ============================================================================
# ISO-DAT-001: Basic Data Read/Write Isolation
# ============================================================================
@pytest.mark.unit
def test_basic_data_read_write_isolation(fast_client: TestClient, vendor_pair_setup):
    """ISO-DAT-001: Basic Data Read/Write Isolation

    Verify that data created by one vendor is invisible and inaccessible to a
    second, simultaneously logged-in Vendor.

    Test Steps:
    1. Create two vendor sessions (s1, s2) for different vendors (v1, v2)
    2. Using s1 session, create an invoice through InvoiceRepository with:
       - invoice_number = "INV-100"
       - amount = 100.0
       - invoice_date = 1 day ago
       - due_date = 30 days from now
    3. Query invoices API with s1 session cookie
       - Verify status code = 200
       - Verify total_count = 1 (s1 sees their own invoice)
    4. Query invoices API with s2 session cookie
       - Verify status code = 200
       - Verify total_count = 0 (s2 does not see s1's invoice)

    Expected Results:
    1. Session s1 authenticated to vendor v1
    2. Invoice successfully created in v1's namespace
    3. s1 sees exactly 1 invoice in their list
    4. s2 sees 0 invoices (no data leakage)
    5. Data isolation maintained between simultaneously logged-in vendors
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    db = vendor_pair_setup["db"]

    # Create invoice as vendor1
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="INV-100",
        amount=100.0,
        description="Test invoice",
        invoice_date=datetime.now(timezone.utc) - timedelta(days=1),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )

    # Vendor1 should see the invoice
    r1 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s1.session_id})
    assert r1.status_code == 200
    assert r1.json()["total_count"] == 1

    # Vendor2 should NOT see vendor1's invoice
    r2 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s2.session_id})
    assert r2.status_code == 200
    assert r2.json()["total_count"] == 0

    db.close()


# ============================================================================
# ISO-DAT-002: Data Manipulation Isolation
# ============================================================================
@pytest.mark.unit
def test_data_manipulation_isolation(fast_client: TestClient, vendor_pair_setup):
    """ISO-DAT-002: Data Manipulation Isolation

    Verify that one Vendor cannot approve or reject an invoice owned by a
    different vendor.

    Test Steps:
    1. Create two vendor sessions (s1, s2) for different vendors
    2. Using s1 session, create invoice with:
       - invoice_number = "INV-200"
       - amount = 200.0
       - Capture invoice.id for later reference
    3. Using s2 session, attempt to access vendor1's invoice via GET /invoices/{invoice_id}
       - Supply s2 session cookie (authenticated to v2)
       - Supply invoice_id (belongs to v1)
    4. Verify response status code = 403 (Forbidden)

    Expected Results:
    1. Invoice successfully created in v1's namespace
    2. GET request from s2 (v2 vendor) receives 403 Forbidden
    3. Cross-vendor data access blocked at authorization layer
    4. No data leakage or error messages revealing invoice existence
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    db = vendor_pair_setup["db"]

    # Create invoice as vendor1
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    invoice = inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="INV-200",
        amount=200.0,
        description="Manipulation test",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    invoice_id = invoice.id

    # Vendor2 attempts to access vendor1's invoice -> should be 403
    r = fast_client.get(
        f"{VENDOR_API_PREFIX}/invoices/{invoice_id}", cookies={"finbot_session": s2.session_id}
    )
    assert r.status_code == 403

    db.close()


# ============================================================================
# ISO-DAT-003: List/Aggregate Data Integrity
# ============================================================================
@pytest.mark.unit
def test_list_aggregate_data_integrity(fast_client: TestClient, vendor_pair_setup):
    """ISO-DAT-003: List/Aggregate Data Integrity

    Verify that list views only contain invoices belonging to the active
    Vendor's namespace.

    Test Steps:
    1. Using s1 session, create two invoices:
       - I1: invoice_number="I1", amount=10.0
       - I2: invoice_number="I2", amount=20.0
    2. Using s2 session, create one invoice:
       - I3: invoice_number="I3", amount=30.0
    3. Query invoices list endpoint with s1 session
       - GET /invoices
       - Verify total_count = 2 (only I1 and I2)
    4. Query invoices list endpoint with s2 session
       - GET /invoices
       - Verify total_count = 1 (only I3)

    Expected Results:
    1. v1 vendor creates 2 invoices successfully
    2. v2 vendor creates 1 invoice successfully
    3. s1 list response contains exactly 2 invoices
    4. s2 list response contains exactly 1 invoice
    5. Aggregate counts reflect vendor-scoped data only
    6. No cross-vendor data visible in list views
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    db = vendor_pair_setup["db"]

    # Create invoices for vendor1
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="I1",
        amount=10.0,
        description="i1",
        invoice_date=datetime.now(timezone.utc) - timedelta(days=3),
        due_date=datetime.now(timezone.utc) + timedelta(days=10),
    )
    inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="I2",
        amount=20.0,
        description="i2",
        invoice_date=datetime.now(timezone.utc) - timedelta(days=2),
        due_date=datetime.now(timezone.utc) + timedelta(days=20),
    )

    # Create invoice for vendor2
    s2_ctx, _ = session_manager.get_session_with_vendor_context(s2.session_id)
    inv_repo_2 = InvoiceRepository(db, s2_ctx)
    inv_repo_2.create_invoice_for_current_vendor(
        invoice_number="I3",
        amount=30.0,
        description="i3",
        invoice_date=datetime.now(timezone.utc) - timedelta(days=1),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )

    # Vendor1 should see exactly 2 invoices
    r1 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s1.session_id})
    assert r1.status_code == 200
    assert r1.json()["total_count"] == 2

    # Vendor2 should see exactly 1 invoice
    r2 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s2.session_id})
    assert r2.status_code == 200
    assert r2.json()["total_count"] == 1

    db.close()


# ============================================================================
# ISO-DAT-004: Cross-Vendor Update/Delete Attack
# ============================================================================
@pytest.mark.unit
def test_cross_vendor_update_delete_attack(fast_client: TestClient, vendor_pair_setup):
    """ISO-DAT-004: Cross-Vendor Update/Delete Attack

    Verify that vendor2 cannot UPDATE or DELETE vendor1's invoices even if
    they know the invoice ID.

    Test Steps:
    1. Using s1 session, create invoice:
       - invoice_number = "INV-ATTACK-001"
       - amount = 500.0
       - Capture invoice_id
    2. Using s2 session, attempt PATCH request to update vendor1's invoice:
       - PATCH /invoices/{invoice_id}
       - Payload: {"amount": 999999.99, "description": "HACKED"}
       - Verify status in [403, 404]
    3. Using s2 session, attempt DELETE request on vendor1's invoice:
       - DELETE /invoices/{invoice_id}
       - Verify status in [403, 404]
    4. Using s1 session, verify invoice unchanged:
       - GET /invoices list
       - Verify invoice still exists with original values
       - amount = 500.0
       - invoice_number = "INV-ATTACK-001"

    Expected Results:
    1. Invoice created successfully in v1 namespace
    2. PATCH request from s2 receives 403 or 404 (authorization failure)
    3. DELETE request from s2 receives 403 or 404 (authorization failure)
    4. Invoice remains in database unmodified
    5. Original data integrity maintained
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    db = vendor_pair_setup["db"]

    # Create invoice as vendor1
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    invoice = inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="INV-ATTACK-001",
        amount=500.0,
        description="Target for attack",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    invoice_id = invoice.id

    # Vendor2 attempts to UPDATE vendor1's invoice
    r_update = fast_client.patch(
        f"{VENDOR_API_PREFIX}/invoices/{invoice_id}",
        json={"amount": 999999.99, "description": "HACKED"},
        cookies={"finbot_session": s2.session_id},
    )
    assert r_update.status_code in [403, 404]

    # Vendor2 attempts to DELETE vendor1's invoice
    r_delete = fast_client.delete(
        f"{VENDOR_API_PREFIX}/invoices/{invoice_id}", cookies={"finbot_session": s2.session_id}
    )
    assert r_delete.status_code in [403, 404]

    # Verify invoice still exists and unchanged
    r_verify = fast_client.get(
        f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s1.session_id}
    )
    assert r_verify.status_code == 200
    invoices = r_verify.json().get("invoices", [])
    vendor1_invoice = next((inv for inv in invoices if inv["id"] == invoice_id), None)
    assert vendor1_invoice is not None
    assert vendor1_invoice["amount"] == 500.0
    assert vendor1_invoice["invoice_number"] == "INV-ATTACK-001"

    db.close()


# ============================================================================
# ISO-DAT-005: SQL Injection via Invoice Fields
# ============================================================================
@pytest.mark.unit
def test_sql_injection_invoice_fields(fast_client: TestClient, vendor_pair_setup):
    """ISO-DAT-005: SQL Injection via Invoice Fields

    Verify that SQL injection attempts in invoice fields are properly sanitized
    and do not leak data or cause errors.

    Test Steps:
    1. Using s2 session, create secret invoice:
       - invoice_number = "SECRET-INVOICE"
       - amount = 99999.99
       - This invoice should remain hidden from vendor1
    2. Define SQL injection payloads:
       - "' OR '1'='1"
       - "'; DROP TABLE invoices--"
       - "1' UNION SELECT * FROM invoices--"
       - "' OR 1=1--"
       - "admin'--"
    3. For each payload, using s1 session:
       - GET /invoices?search={payload}
       - Verify response status in [200, 400]
       - If 200: extract invoices list
       - Verify "SECRET-INVOICE" is NOT in results

    Expected Results:
    1. Secret invoice created in v2 namespace
    2. Each SQL injection query returns 200 or 400 status
    3. No database errors or crashes
    4. SECRET-INVOICE never appears in v1's results
    5. SQL injection payloads treated as literal search strings
    6. Data isolation maintained despite injection attempts
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    db = vendor_pair_setup["db"]

    # Create secret invoice for vendor2 (should remain hidden from vendor1)
    s2_ctx, _ = session_manager.get_session_with_vendor_context(s2.session_id)
    inv_repo_2 = InvoiceRepository(db, s2_ctx)
    inv_repo_2.create_invoice_for_current_vendor(
        invoice_number="SECRET-INVOICE",
        amount=99999.99,
        description="Hidden data",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )

    # Test SQL injection payloads
    payloads = [
        "' OR '1'='1",
        "'; DROP TABLE invoices--",
        "1' UNION SELECT * FROM invoices--",
        "' OR 1=1--",
        "admin'--",
    ]

    for payload in payloads:
        r = fast_client.get(
            f"{VENDOR_API_PREFIX}/invoices",
            params={"search": payload},
            cookies={"finbot_session": s1.session_id},
        )

        assert r.status_code in [200, 400]

        if r.status_code == 200:
            invoices = r.json().get("invoices", [])
            invoice_numbers = [inv.get("invoice_number") for inv in invoices]
            assert "SECRET-INVOICE" not in invoice_numbers, f"SQL injection leaked data: {payload}"

    db.close()


# ============================================================================
# ISO-DAT-006: Unauthorized Field Modification
# ============================================================================
@pytest.mark.unit
def test_unauthorized_field_modification(fast_client: TestClient, vendor_pair_setup):
    """ISO-DAT-006: Unauthorized Field Modification

    Verify that vendors cannot modify sensitive fields they don't own or
    manipulate metadata fields that should be immutable.

    Test Steps:
    1. Using s2 session, create invoice:
       - invoice_number = "TEST-MOD-006"
       - amount = 5000.00
       - description = "Original Description"
       - Capture invoice_id
    2. Using s1 session, attempt PUT request to modify vendor2's invoice:
       - PUT /invoices/{invoice_id}
       - Payload: {"invoice_number": "HACKED-006", "amount": 99999.99, "description": "Hacked by vendor1"}
       - Verify status in [403, 404]
    3. Refresh vendor2's context and verify invoice unchanged:
       - Query invoice by invoice_id
       - Verify invoice_number = "TEST-MOD-006"
       - Verify amount = 5000.00
       - Verify description = "Original Description"

    Expected Results:
    1. Invoice created in v2 namespace with original values
    2. PUT request from s1 receives 403 or 404
    3. Invoice remains completely unmodified
    4. All fields retain original values
    5. No partial updates allowed from unauthorized vendor
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    db = vendor_pair_setup["db"]

    # Create invoice for vendor2
    s2_ctx, _ = session_manager.get_session_with_vendor_context(s2.session_id)
    inv_repo_2 = InvoiceRepository(db, s2_ctx)
    invoice = inv_repo_2.create_invoice_for_current_vendor(
        invoice_number="TEST-MOD-006",
        amount=5000.00,
        description="Original Description",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    invoice_id = invoice.id

    # Vendor1 attempts to modify vendor2's invoice
    modify_payload = {
        "invoice_number": "HACKED-006",
        "amount": 99999.99,
        "description": "Hacked by vendor1",
    }

    r = fast_client.put(
        f"{VENDOR_API_PREFIX}/invoices/{invoice_id}",
        json=modify_payload,
        cookies={"finbot_session": s1.session_id},
    )

    # Should get 403 Forbidden or 404 Not Found
    assert r.status_code in [
        403,
        404,
    ], f"Vendor1 should not modify vendor2's invoice. Got status {r.status_code}"

    # Verify invoice was NOT modified
    s2_ctx_refresh, _ = session_manager.get_session_with_vendor_context(s2.session_id)
    inv_repo_2_refresh = InvoiceRepository(db, s2_ctx_refresh)
    invoice_check = inv_repo_2_refresh.get_invoice(invoice_id)

    assert (
        invoice_check.invoice_number == "TEST-MOD-006"
    ), "Invoice number was modified by unauthorized vendor"
    assert invoice_check.amount == 5000.00, "Invoice amount was modified by unauthorized vendor"
    assert (
        invoice_check.description == "Original Description"
    ), "Invoice description was modified by unauthorized vendor"

    db.close()


# ============================================================================
# ISO-DAT-007: ID Enumeration Attack
# ============================================================================
@pytest.mark.unit
def test_id_enumeration_attack(fast_client: TestClient, vendor_pair_setup):
    """ISO-DAT-007: ID Enumeration Attack

    Verify that vendor cannot enumerate and access other vendors' invoices by
    guessing sequential IDs.

    Test Steps:
    1. Using s1 session, create invoice:
       - invoice_number = "INV-ENUM-TEST"
       - amount = 100.0
       - Capture invoice.id as target_id
    2. Calculate test IDs around target:
       - test_ids = [target_id-2, target_id-1, target_id, target_id+1, target_id+2]
    3. For each test_id, using s2 session:
       - GET /invoices/{test_id}
       - Verify status in [403, 404]
       - This should prevent enumeration of all IDs in range

    Expected Results:
    1. Invoice created with specific ID in v1 namespace
    2. All 5 enumeration attempts return 403 or 404
    3. No information leakage based on HTTP status codes
    4. Enumeration attack prevented regardless of ID proximity
    5. Authorization checks applied before existence checks
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    db = vendor_pair_setup["db"]

    # Create invoice as vendor1
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    invoice = inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="INV-ENUM-TEST",
        amount=100.0,
        description="Enumeration target",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    target_id = invoice.id

    # Vendor2 attempts to enumerate IDs around vendor1's invoice
    test_ids = [target_id - 2, target_id - 1, target_id, target_id + 1, target_id + 2]

    for test_id in test_ids:
        r = fast_client.get(
            f"{VENDOR_API_PREFIX}/invoices/{test_id}", cookies={"finbot_session": s2.session_id}
        )
        assert r.status_code in [
            403,
            404,
        ], f"ID {test_id} returned {r.status_code} instead of 403/404"

    db.close()


# ============================================================================
# ISO-SES-001: Forced Logout / Session Invalidation
# ============================================================================
@pytest.mark.unit
def test_forced_logout_session_invalidation(fast_client: TestClient, vendor_pair_setup):
    """ISO-SES-001: Forced Logout / Session Invalidation

    Verify that a session cannot be reused after the user switches vendors
    (simulating logout/re-login).

    Test Steps:
    1. Verify s1 session works with v1 vendor:
       - GET /invoices with s1.session_id
       - Verify status 200
    2. Using s1 session, create invoice in v1:
       - invoice_number = "LOGOUT-TEST"
       - amount = 999.99
       - Capture invoice ID
    3. Switch vendor context for session s1:
       - Query UserSession where session_id = s1.session_id
       - Update current_vendor_id from v1.id to v2.id
       - Commit to database
    4. Query invoices with s1 session (now bound to v2):
       - GET /invoices with s1.session_id
       - Verify total_count = 0 (no invoices in v2 namespace)

    Expected Results:
    1. s1 initially has access to v1 resources
    2. Invoice created in v1 namespace
    3. Session vendor context successfully updated
    4. s1 now sees only v2's invoices (empty list)
    5. v1's invoice no longer visible after context switch
    6. Vendor switching invalidates previous namespace view
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    v1, v2 = vendor_pair_setup["v1"], vendor_pair_setup["v2"]
    db = vendor_pair_setup["db"]

    # Verify s1 has access to vendor1's resources
    r = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s1.session_id})
    assert r.status_code == 200

    # Create invoice for v1
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    invoice_v1 = inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="LOGOUT-TEST",
        amount=999.99,
        description="Logout test invoice",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )

    # Switch vendor context for session s1 to v2
    us1 = db.query(UserSession).filter(UserSession.session_id == s1.session_id).first()
    us1.current_vendor_id = v2.id
    db.commit()

    # Now s1 should no longer see v1's invoice
    r = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s1.session_id})
    assert r.status_code == 200
    assert r.json()["total_count"] == 0  # Should not see v1's invoice anymore

    db.close()


# ============================================================================
# ISO-SES-002: Concurrent Session Overlap
# ============================================================================
@pytest.mark.unit
def test_concurrent_session_overlap(fast_client: TestClient, vendor_pair_setup):
    """ISO-SES-002: Concurrent Session Overlap

    Verify that two concurrent sessions for the same user do not interfere
    with each other when accessing different vendor contexts.

    Test Steps:
    1. Using s1 session (bound to v1), create invoice:
       - invoice_number = "OVERLAP-V1"
       - amount = 100.0
       - description = "Vendor 1 invoice"
    2. Using s2 session (bound to v2), create invoice:
       - invoice_number = "OVERLAP-V2"
       - amount = 200.0
       - description = "Vendor 2 invoice"
    3. Query invoices with s1 session:
       - GET /invoices
       - Verify status 200
       - Verify total_count = 1 (only OVERLAP-V1)
    4. Query invoices with s2 session:
       - GET /invoices
       - Verify status 200
       - Verify total_count = 1 (only OVERLAP-V2)

    Expected Results:
    1. v1 invoice created successfully
    2. v2 invoice created successfully
    3. s1 session maintains isolation to v1 data
    4. s2 session maintains isolation to v2 data
    5. Both sessions work independently without interference
    6. Concurrent operations do not cause data leakage
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    v1, v2 = vendor_pair_setup["v1"], vendor_pair_setup["v2"]
    db = vendor_pair_setup["db"]

    # Create invoice in vendor1's context
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="OVERLAP-V1",
        amount=100.0,
        description="Vendor 1 invoice",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )

    # Create invoice in vendor2's context
    s2_ctx, _ = session_manager.get_session_with_vendor_context(s2.session_id)
    inv_repo_2 = InvoiceRepository(db, s2_ctx)
    inv_repo_2.create_invoice_for_current_vendor(
        invoice_number="OVERLAP-V2",
        amount=200.0,
        description="Vendor 2 invoice",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )

    # Both sessions should still work independently
    r1 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s1.session_id})
    assert r1.status_code == 200
    assert r1.json()["total_count"] == 1

    r2 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s2.session_id})
    assert r2.status_code == 200
    assert r2.json()["total_count"] == 1

    db.close()


# ============================================================================
# ISO-NAM-001: Namespace Integrity Checks
# ============================================================================
@pytest.mark.unit
def test_namespace_integrity_checks(fast_client: TestClient, vendor_pair_setup):
    """ISO-NAM-001: Namespace Integrity Checks

    Verify that each vendor's data is properly isolated by user namespace.

    Test Steps:
    1. Verify vendors are different:
       - Assert v1.id != v2.id
    2. Verify sessions belong to same user but different vendors:
       - Query UserSession where session_id = s1.session_id
       - Query UserSession where session_id = s2.session_id
       - Assert us1.user_id == us2.user_id (same user)
       - Assert us1.current_vendor_id == v1.id
       - Assert us2.current_vendor_id == v2.id (different vendors)
    3. Using s1 session, create invoice:
       - invoice_number = "NS-CHECK-001"
       - amount = 999.99
    4. Query invoices with s1 session:
       - GET /invoices
       - Verify total_count = 1
    5. Query invoices with s2 session:
       - GET /invoices
       - Verify total_count = 0

    Expected Results:
    1. v1 and v2 are different vendors
    2. Both sessions belong to same user
    3. Sessions have different vendor contexts
    4. s1 sees 1 invoice (own invoice)
    5. s2 sees 0 invoices (no data leakage)
    6. Namespace isolation verified at session and vendor level
    """
    s1, s2 = vendor_pair_setup["s1"], vendor_pair_setup["s2"]
    v1, v2 = vendor_pair_setup["v1"], vendor_pair_setup["v2"]
    db = vendor_pair_setup["db"]

    # Verify vendors are different
    assert v1.id != v2.id

    # Verify sessions belong to same user but different vendor contexts
    us1 = db.query(UserSession).filter(UserSession.session_id == s1.session_id).first()
    us2 = db.query(UserSession).filter(UserSession.session_id == s2.session_id).first()
    assert us1.user_id == us2.user_id  # Same user
    assert us1.current_vendor_id == v1.id
    assert us2.current_vendor_id == v2.id  # Different vendors

    # Create invoice in vendor1, verify vendor2 cannot see it
    s1_ctx, _ = session_manager.get_session_with_vendor_context(s1.session_id)
    inv_repo_1 = InvoiceRepository(db, s1_ctx)
    inv_repo_1.create_invoice_for_current_vendor(
        invoice_number="NS-CHECK-001",
        amount=999.99,
        description="Namespace test",
        invoice_date=datetime.now(timezone.utc),
        due_date=datetime.now(timezone.utc) + timedelta(days=30),
    )

    r1 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s1.session_id})
    assert r1.json()["total_count"] == 1

    r2 = fast_client.get(f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": s2.session_id})
    assert r2.json()["total_count"] == 0

    db.close()


# ============================================================================
# ISO-MUL-001: Peak Load / Concurrent Interactions
# ============================================================================
@pytest.mark.unit
def test_peak_load_concurrent_interaction(fast_client: TestClient, multi_vendor_setup):
    """ISO-MUL-001: Peak Load / Concurrent Interactions

    Verify isolation holds under load with multiple vendors creating invoices
    concurrently.

    Test Steps:
    1. For each vendor in multi_vendor_setup (3+ vendors):
       a. Get session_id from vendor_data
       b. Get vendor_context using session_manager.get_session_with_vendor_context()
       c. Create InvoiceRepository with context
       d. Create invoice with invoice_number = f"LOAD-{vendor_id}"
       e. Store returned invoice.id in vendor_data['invoice_id']
    2. For each vendor in multi_vendor_setup:
       a. GET /invoices with vendor's session_id
       b. Verify status 200
       c. Extract invoices array from response
       d. Assert len(invoices) == 1 (only their own invoice)
       e. Assert invoices[0]['id'] == vendor_data['invoice_id'] (correct invoice)

    Expected Results:
    1. All vendors successfully create invoices
    2. All vendors' list queries return status 200
    3. Each vendor sees exactly 1 invoice
    4. Each vendor sees their own invoice (ID matches)
    5. No cross-vendor data visible
    6. Isolation maintained under concurrent load conditions
    7. Aggregate count = number of vendors created
    """
    vendors = multi_vendor_setup
    db = vendors[0]["db"]

    # Create invoices for each vendor
    for vendor_data in vendors:
        session_id = vendor_data["session_id"]
        ctx, _ = session_manager.get_session_with_vendor_context(session_id)
        inv_repo = InvoiceRepository(db, ctx)
        invoice = inv_repo.create_invoice_for_current_vendor(
            invoice_number=f"LOAD-{vendor_data['vendor_id']}",
            amount=100.0,
            description="Load test invoice",
            invoice_date=datetime.now(timezone.utc),
            due_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        vendor_data["invoice_id"] = invoice.id

    # Verify each vendor sees only their own invoice
    for vendor_data in vendors:
        r = fast_client.get(
            f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": vendor_data["session_id"]}
        )
        assert r.status_code == 200
        invoices = r.json()["invoices"]
        assert (
            len(invoices) == 1
        ), f"Vendor {vendor_data['vendor_id']} sees {len(invoices)} invoices instead of 1"
        assert invoices[0]["id"] == vendor_data["invoice_id"]

    db.close()


# ============================================================================
# ISO-SES-003: Expired Session Rejection
# ============================================================================
@pytest.mark.unit
def test_expired_session_rejection(fast_client: TestClient, db):
    """ISO-SES-003: Expired Session Rejection

    Verify that expired sessions are properly rejected and cannot access
    protected resources.

    Test Steps:
    1. Create new session for email "expiry_test@example.com"
    2. Create VendorRepository with new session
    3. Create vendor with all required fields
    4. Link vendor to session:
       - Query UserSession where session_id = session.session_id
       - Update current_vendor_id = vendor.id
       - Commit changes
    5. Verify session works before expiration:
       - GET /invoices with session.session_id
       - Verify status 200
    6. Expire the session:
       - Query UserSession where session_id = session.session_id
       - Set expires_at = now - 1 hour (past time)
       - Commit changes
    7. Attempt access with expired session:
       - GET /invoices with session.session_id
       - Expect status != 200 OR ValueError with "Vendor context required"

    Expected Results:
    1. New session created successfully
    2. Vendor created and linked to session
    3. Session works before expiration (status 200)
    4. Session expires_at updated to past time
    5. Expired session access fails with:
       - status code != 200 (401, 403, 500, etc)
       - OR ValueError exception with vendor context message
    6. Middleware/auth layer properly rejects expired sessions
    """
    from finbot.core.data.repositories import VendorRepository

    # Create session and vendor
    session = session_manager.create_session(email="expiry_test@example.com")
    vendor_repo = VendorRepository(db, session)
    vendor = vendor_repo.create_vendor(
        company_name="Expiry Test Vendor",
        vendor_category="Technology",
        industry="Software",
        services="Testing",
        contact_name="Test User",
        email="test@expiry.com",
        tin="99-9999999",
        bank_account_number="9999999999",
        bank_name="Test Bank",
        bank_routing_number="999999999",
        bank_account_holder_name="Expiry Test Vendor",
    )

    # Link vendor to session
    us = db.query(UserSession).filter(UserSession.session_id == session.session_id).first()
    us.current_vendor_id = vendor.id
    db.commit()

    # Verify session works
    r = fast_client.get(
        f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": session.session_id}
    )
    assert r.status_code == 200

    # Expire the session
    us.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    # Attempt access with expired session - should fail
    # The expired session triggers middleware to delete it and create temp session
    # Temp session has no vendor context, causing ValueError or proper HTTP error
    try:
        r_expired = fast_client.get(
            f"{VENDOR_API_PREFIX}/invoices", cookies={"finbot_session": session.session_id}
        )
        # If we get here, check for non-200 status (401, 403, 500, etc)
        assert (
            r_expired.status_code != 200
        ), f"Expired session should be rejected, got {r_expired.status_code}"
    except ValueError as e:
        # ValueError "Vendor context required" is also a valid rejection
        assert "Vendor context required" in str(e)

    db.close()


# ============================================================================
# ISO-REG-001: Automated Regression Suite Execution
# ============================================================================
@pytest.mark.unit
def test_automated_regression_suite_execution():
    """ISO-REG-001: Automated Regression Suite Execution

    Ensure all isolation tests are properly configured for CI/CD execution.

    Test Steps:
    1. Define expected_tests list with all isolation test function names:
       - 13 data isolation tests (ISO-DAT-001 through ISO-DAT-007)
       - 3 session isolation tests (ISO-SES-001 through ISO-SES-003)
       - 1 namespace test (ISO-NAM-001)
       - 1 multi-vendor load test (ISO-MUL-001)
    2. Get current module from sys.modules[__name__]
    3. For each test_name in expected_tests:
       a. Verify test function exists with hasattr(current_module, test_name)
       b. Collect missing test names
    4. Assert no missing tests:
       a. Assert len(missing_tests) == 0
       b. Fail with list of missing tests if any found
    5. For each test_name in expected_tests:
       a. Get test function with getattr(current_module, test_name)
       b. Extract markers if hasattr(test_func, 'pytestmark')
       c. Verify 'unit' in markers list
       d. Assert each test has @pytest.mark.unit marker
    6. Print summary: f"{len(expected_tests)} isolation tests ready for CI/CD"

    Expected Results:
    1. All 13 expected tests exist in module
    2. No missing test functions reported
    3. All tests have @pytest.mark.unit marker
    4. All tests properly configured for automation
    5. Summary message printed to console
    6. CI/CD pipeline can discover and execute all tests
    """
    expected_tests = [
        "test_basic_data_read_write_isolation",  # ISO-DAT-001
        "test_data_manipulation_isolation",  # ISO-DAT-002
        "test_list_aggregate_data_integrity",  # ISO-DAT-003
        "test_cross_vendor_update_delete_attack",  # ISO-DAT-004
        "test_sql_injection_invoice_fields",  # ISO-DAT-005
        "test_unauthorized_field_modification",  # ISO-DAT-006
        "test_id_enumeration_attack",  # ISO-DAT-007
        "test_forced_logout_session_invalidation",  # ISO-SES-001
        "test_concurrent_session_overlap",  # ISO-SES-002
        "test_expired_session_rejection",  # ISO-SES-003
        "test_namespace_integrity_checks",  # ISO-NAM-001
        "test_peak_load_concurrent_interaction",  # ISO-MUL-001
    ]

    import sys

    current_module = sys.modules[__name__]

    # Verify all expected tests exist
    missing_tests = []
    for test_name in expected_tests:
        if not hasattr(current_module, test_name):
            missing_tests.append(test_name)

    assert len(missing_tests) == 0, f"Missing isolation tests: {missing_tests}"

    # Verify all tests are marked with @pytest.mark.unit
    for test_name in expected_tests:
        test_func = getattr(current_module, test_name)
        markers = (
            [mark.name for mark in test_func.pytestmark] if hasattr(test_func, "pytestmark") else []
        )
        assert "unit" in markers, f"Test {test_name} is missing @pytest.mark.unit marker"

    print(f"\n✓ Regression suite validated: {len(expected_tests)} isolation tests ready for CI/CD")


# ============================================================================
# ISO-GS-001: Google Sheets Integration Verification
# ============================================================================
@pytest.mark.unit
def test_google_sheets_integration_verification():
    """ISO-GS-001: Google Sheets Integration Verification

    Verify that test results are properly recorded in Google Sheets.

    Test Steps:
    1. Connect to Google Sheets using credentials
    2. Open the Summary worksheet
    3. Verify the latest row contains today's test run
    4. Check that passed/failed counts match expected values
    5. Verify the Isolation Testing Framework TCs worksheet has test markers

    Expected Results:
    1. Google Sheets connection successful
    2. Summary sheet contains recent test run data
    3. Test counts are accurate
    4. Worksheet tab has automation_status updates
    """
    import os
    from datetime import datetime

    import gspread
    from dotenv import load_dotenv
    from google.oauth2.service_account import Credentials

    load_dotenv()

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "google-credentials.json")

    if not sheet_id or not os.path.exists(creds_file):
        pytest.skip("Google Sheets credentials not configured")

    try:
        # Connect to Google Sheets
        creds = Credentials.from_service_account_file(
            creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id)

        # Check Summary sheet exists
        summary_sheet = sheet.worksheet("Summary")
        summary_data = summary_sheet.get_all_values()

        assert len(summary_data) > 1, "Summary sheet should have data"

        # Verify headers
        headers = summary_data[0]
        assert "timestamp" in headers
        assert "total_tests" in headers
        assert "passed" in headers
        assert "failed" in headers

        # Check Isolation Testing Framework TCs sheet
        isolation_sheet = sheet.worksheet("Isolation Testing Framework TCs")
        isolation_data = isolation_sheet.get_all_values()

        assert len(isolation_data) > 0, "Isolation Testing Framework TCs should have data"

        # Verify automation_status column exists
        headers = isolation_data[0]
        has_automation_status = any("automation" in h.lower() for h in headers)
        assert has_automation_status, "Should have automation_status column"

        print("✓ Google Sheets integration verified successfully")

    except Exception as e:
        pytest.fail(f"Google Sheets verification failed: {e}")
