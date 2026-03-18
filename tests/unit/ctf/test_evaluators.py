"""
Unit tests for finbot/ctf/evaluators/implementations/

Tests all four badge evaluators: InvoiceCountEvaluator, InvoiceAmountEvaluator,
VendorCountEvaluator, and ChallengeCompletionEvaluator.
All tests use in-memory SQLite via the shared db fixture.
"""

import pytest
from datetime import date

from finbot.core.auth.session import session_manager
from finbot.core.data.models import Challenge, Invoice, UserChallengeProgress, Vendor
from finbot.ctf.evaluators.implementations.invoice_count import InvoiceCountEvaluator
from finbot.ctf.evaluators.implementations.invoice_amount import InvoiceAmountEvaluator
from finbot.ctf.evaluators.implementations.vendor_count import VendorCountEvaluator
from finbot.ctf.evaluators.implementations.challenge_completion import (
    ChallengeCompletionEvaluator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_vendor_counter = 0


def _make_vendor(db, namespace, status="active"):
    global _vendor_counter
    _vendor_counter += 1
    vendor = Vendor(
        namespace=namespace,
        company_name=f"Vendor {_vendor_counter}",
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Alice",
        email=f"vendor{_vendor_counter}@test.com",
        tin="12-3456789",
        bank_account_number=f"1234567890{_vendor_counter:02d}",
        bank_name="Test Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Alice",
        status=status,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


def _make_invoice(db, namespace, amount=1000.0, status="submitted", vendor_id=None):
    if vendor_id is None:
        vendor = _make_vendor(db, namespace)
        vendor_id = vendor.id
    invoice = Invoice(
        namespace=namespace,
        vendor_id=vendor_id,
        description="Test invoice",
        amount=amount,
        status=status,
        invoice_date=date.today(),
        due_date=date.today(),
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def _make_challenge(db, challenge_id, category="recon"):
    challenge = Challenge(
        id=challenge_id,
        title=f"Challenge {challenge_id}",
        description="A test challenge description",
        category=category,
        difficulty="beginner",
        detector_class="MockDetector",
    )
    db.add(challenge)
    db.commit()
    return challenge


def _make_progress(db, namespace, user_id, challenge_id, status="completed"):
    progress = UserChallengeProgress(
        namespace=namespace,
        user_id=user_id,
        challenge_id=challenge_id,
        status=status,
    )
    db.add(progress)
    db.commit()
    db.refresh(progress)
    return progress


def _event(namespace="ns-test", user_id="user-abc"):
    return {"namespace": namespace, "user_id": user_id}


# ===========================================================================
# InvoiceCountEvaluator
# ===========================================================================


class TestInvoiceCountEvaluator:

    @pytest.mark.unit
    def test_eval_ic_001_config_requires_min_count(self):
        """EVAL-IC-001: InvoiceCountEvaluator raises ValueError when min_count missing

        Title: InvoiceCountEvaluator validates that min_count is in config
        Basically question: Does InvoiceCountEvaluator raise ValueError at
                            init time when config has no min_count?
        Steps:
        1. Instantiate InvoiceCountEvaluator with empty config
        Expected Results:
        1. ValueError raised with "min_count is required"

        Impact: Without config validation, misconfigured badges silently award
                themselves or never award.
        """
        with pytest.raises(ValueError, match="min_count is required"):
            InvoiceCountEvaluator("badge-test", config={})

    @pytest.mark.unit
    def test_eval_ic_002_invalid_invoice_status_rejected(self):
        """EVAL-IC-002: InvoiceCountEvaluator rejects invalid invoice_status

        Title: InvoiceCountEvaluator validates invoice_status in config
        Basically question: Does InvoiceCountEvaluator raise ValueError when
                            invoice_status is not a valid status?
        Steps:
        1. Instantiate with invoice_status="bogus"
        Expected Results:
        1. ValueError raised

        Impact: Invalid status filter silently matches nothing — badge never awards.
        """
        with pytest.raises(ValueError):
            InvoiceCountEvaluator("badge-test", config={"min_count": 1, "invoice_status": "bogus"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ic_003_detected_when_count_met(self, db):
        """EVAL-IC-003: InvoiceCountEvaluator detects when invoice count >= min_count

        Title: InvoiceCountEvaluator returns detected=True when threshold met
        Basically question: Does InvoiceCountEvaluator return detected=True
                            when the namespace has enough invoices?
        Steps:
        1. Create 3 invoices in namespace "ns-test"
        2. Instantiate with min_count=3
        3. Call check_event
        Expected Results:
        1. detected=True, confidence=1.0
        2. evidence includes invoice_count=3

        Impact: If detection fails, badge is never awarded regardless of progress.
        """
        for _ in range(3):
            _make_invoice(db, "ns-test")

        evaluator = InvoiceCountEvaluator("badge-test", config={"min_count": 3})
        result = await evaluator.check_event(_event("ns-test"), db)

        assert result.detected is True
        assert result.confidence == 1.0
        assert result.evidence["invoice_count"] == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ic_004_not_detected_when_count_below_min(self, db):
        """EVAL-IC-004: InvoiceCountEvaluator not detected when count < min_count

        Title: InvoiceCountEvaluator returns detected=False when threshold not met
        Basically question: Does InvoiceCountEvaluator return detected=False
                            with partial confidence when count is below min_count?
        Steps:
        1. Create 1 invoice in namespace "ns-partial"
        2. Instantiate with min_count=5
        3. Call check_event
        Expected Results:
        1. detected=False
        2. confidence == 1/5 == 0.2

        Impact: If partial confidence is wrong, progress bars show inaccurate data.
        """
        _make_invoice(db, "ns-partial")

        evaluator = InvoiceCountEvaluator("badge-test", config={"min_count": 5})
        result = await evaluator.check_event(_event("ns-partial"), db)

        assert result.detected is False
        assert result.confidence == pytest.approx(0.2)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ic_005_missing_namespace_not_detected(self, db):
        """EVAL-IC-005: InvoiceCountEvaluator returns not-detected for missing namespace

        Title: InvoiceCountEvaluator handles missing namespace in event
        Basically question: Does InvoiceCountEvaluator return detected=False
                            (not raise) when event has no namespace?
        Steps:
        1. Call check_event with event missing "namespace" key
        Expected Results:
        1. detected=False, no exception

        Impact: Missing namespace would crash the event pipeline if not handled.
        """
        evaluator = InvoiceCountEvaluator("badge-test", config={"min_count": 1})
        result = await evaluator.check_event({}, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ic_006_status_filter_applied(self, db):
        """EVAL-IC-006: InvoiceCountEvaluator filters by invoice_status

        Title: InvoiceCountEvaluator only counts invoices matching status filter
        Basically question: Does InvoiceCountEvaluator exclude invoices whose
                            status does not match invoice_status config?
        Steps:
        1. Create 2 approved and 1 submitted invoice in "ns-filter"
        2. Instantiate with min_count=2, invoice_status="approved"
        3. Call check_event
        Expected Results:
        1. detected=True (2 approved >= min_count=2)
        2. evidence["invoice_count"] == 2

        Impact: Without status filter, badges for "approved" invoices award
                as soon as invoices are submitted — before any agent review.
        """
        _make_invoice(db, "ns-filter", status="approved")
        _make_invoice(db, "ns-filter", status="approved")
        _make_invoice(db, "ns-filter", status="submitted")

        evaluator = InvoiceCountEvaluator(
            "badge-test", config={"min_count": 2, "invoice_status": "approved"}
        )
        result = await evaluator.check_event(_event("ns-filter"), db)

        assert result.detected is True
        assert result.evidence["invoice_count"] == 2

    @pytest.mark.unit
    def test_eval_ic_007_get_progress_returns_correct_fields(self, db):
        """EVAL-IC-007: InvoiceCountEvaluator.get_progress returns current/target/percentage

        Title: get_progress returns structured progress dict
        Basically question: Does get_progress return the right fields with
                            correct percentage calculation?
        Steps:
        1. Create 2 invoices in "ns-prog"
        2. Instantiate with min_count=4
        3. Call get_progress
        Expected Results:
        1. current == 2, target == 4, percentage == 50

        Impact: Wrong progress data misleads players about how close they are.
        """
        _make_invoice(db, "ns-prog")
        _make_invoice(db, "ns-prog")

        evaluator = InvoiceCountEvaluator("badge-test", config={"min_count": 4})
        progress = evaluator.get_progress("ns-prog", "user-abc", db)

        assert progress["current"] == 2
        assert progress["target"] == 4
        assert progress["percentage"] == 50

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ic_008_counts_all_namespace_invoices_regardless_of_user(self, db):
        """EVAL-IC-008: InvoiceCountEvaluator counts all invoices in the namespace, not just the current user's

        Title: InvoiceCountEvaluator does not filter by user_id — namespace-wide count
        Description: The evaluator counts every invoice in the namespace, regardless of which
                     user created them. In a shared namespace, invoices from any team member
                     count toward the badge. This test documents that behavior so it is explicit
                     and intentional rather than a hidden surprise.
        Basically question: Does InvoiceCountEvaluator count invoices created by other users
                            in the same namespace toward the badge threshold?
        Steps:
        1. Create 3 invoices in "ns-shared-inv" (no user_id association on the Invoice model)
        2. Call check_event with user_id="user-A" and min_count=3
        Expected Results:
        1. detected=True — all namespace invoices are counted regardless of user_id

        Impact: Challenge authors should be aware that this evaluator operates at namespace
                scope. If per-user isolation is needed, use ChallengeCompletionEvaluator
                which does filter by user_id.
        """
        for _ in range(3):
            _make_invoice(db, "ns-shared-inv")

        evaluator = InvoiceCountEvaluator("badge-test", config={"min_count": 3})
        result = await evaluator.check_event(_event("ns-shared-inv", "user-A"), db)
        assert result.detected is True


# ===========================================================================
# InvoiceAmountEvaluator
# ===========================================================================


class TestInvoiceAmountEvaluator:

    @pytest.mark.unit
    def test_eval_ia_001_config_requires_min_amount(self):
        """EVAL-IA-001: InvoiceAmountEvaluator raises ValueError when min_amount missing

        Title: InvoiceAmountEvaluator validates that min_amount is in config
        Basically question: Does InvoiceAmountEvaluator raise ValueError at
                            init time when config has no min_amount?
        Steps:
        1. Instantiate with empty config
        Expected Results:
        1. ValueError raised with "min_amount is required"

        Impact: Misconfigured badge silently never awards.
        """
        with pytest.raises(ValueError, match="min_amount is required"):
            InvoiceAmountEvaluator("badge-test", config={})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ia_002_detected_when_amount_met(self, db):
        """EVAL-IA-002: InvoiceAmountEvaluator detects when total amount >= min_amount

        Title: InvoiceAmountEvaluator returns detected=True when threshold met
        Basically question: Does InvoiceAmountEvaluator sum invoice amounts
                            and detect when total meets min_amount?
        Steps:
        1. Create invoices totaling $1500 in "ns-amount"
        2. Instantiate with min_amount=1000
        3. Call check_event
        Expected Results:
        1. detected=True, confidence=1.0
        2. evidence["total_amount"] == 1500.0

        Impact: If detection fails, amount-based badges never award.
        """
        _make_invoice(db, "ns-amount", amount=800.0)
        _make_invoice(db, "ns-amount", amount=700.0)

        evaluator = InvoiceAmountEvaluator("badge-test", config={"min_amount": 1000})
        result = await evaluator.check_event(_event("ns-amount"), db)

        assert result.detected is True
        assert result.evidence["total_amount"] == 1500.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ia_003_not_detected_below_threshold(self, db):
        """EVAL-IA-003: InvoiceAmountEvaluator not detected when total < min_amount

        Title: InvoiceAmountEvaluator returns detected=False with partial confidence
        Basically question: Does InvoiceAmountEvaluator return detected=False
                            and correct partial confidence below threshold?
        Steps:
        1. Create $200 invoice in "ns-low"
        2. Instantiate with min_amount=1000
        3. Call check_event
        Expected Results:
        1. detected=False, confidence == 0.2

        Impact: Incorrect confidence breaks progress bar.
        """
        _make_invoice(db, "ns-low", amount=200.0)

        evaluator = InvoiceAmountEvaluator("badge-test", config={"min_amount": 1000})
        result = await evaluator.check_event(_event("ns-low"), db)

        assert result.detected is False
        assert result.confidence == pytest.approx(0.2)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ia_004_status_filter_applied(self, db):
        """EVAL-IA-004: InvoiceAmountEvaluator filters by invoice_status

        Title: InvoiceAmountEvaluator only sums invoices matching status filter
        Basically question: Does invoice_status config correctly exclude invoices
                            whose status does not match?
        Steps:
        1. Create $800 approved and $500 submitted invoice in "ns-amtfilter"
        2. Instantiate with min_amount=500, invoice_status="approved"
        3. Call check_event
        Expected Results:
        1. detected=True (only $800 counted, > $500)
        2. total_amount == 800.0

        Impact: Without filter, unreviewed invoices count toward payment badges.
        """
        _make_invoice(db, "ns-amtfilter", amount=800.0, status="approved")
        _make_invoice(db, "ns-amtfilter", amount=500.0, status="submitted")

        evaluator = InvoiceAmountEvaluator(
            "badge-test", config={"min_amount": 500, "invoice_status": "approved"}
        )
        result = await evaluator.check_event(_event("ns-amtfilter"), db)

        assert result.detected is True
        assert result.evidence["total_amount"] == 800.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ia_005_zero_invoices_returns_zero_total(self, db):
        """EVAL-IA-005: InvoiceAmountEvaluator returns total_amount=0 when no invoices

        Title: InvoiceAmountEvaluator handles empty namespace gracefully
        Basically question: Does InvoiceAmountEvaluator return 0 (not None/error)
                            when namespace has no invoices?
        Steps:
        1. Call check_event for namespace "ns-empty-amt" with no invoices
        Expected Results:
        1. detected=False, no exception

        Impact: None/crash on empty namespace breaks badge processing pipeline.
        """
        evaluator = InvoiceAmountEvaluator("badge-test", config={"min_amount": 100})
        result = await evaluator.check_event(_event("ns-empty-amt"), db)

        assert result.detected is False
        assert result.evidence["total_amount"] == 0.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_ia_006_counts_all_namespace_invoices_regardless_of_user(self, db):
        """EVAL-IA-006: InvoiceAmountEvaluator sums all invoice amounts in the namespace, not just the current user's

        Title: InvoiceAmountEvaluator does not filter by user_id — namespace-wide sum
        Description: check_event never reads user_id from the event. _sum_invoices filters only
                     on namespace, so the badge fires as soon as the namespace-wide invoice total
                     reaches min_amount — regardless of which user submitted those invoices.
                     A player in a shared namespace benefits from their teammates' invoices.
        Basically question: Does InvoiceAmountEvaluator award the badge based on the total
                            invoice amount across the whole namespace, not just the current user's invoices?
        Steps:
        1. Create 2 invoices in "ns-shared-amt" with amounts $600 each (total $1200)
        2. Call check_event with user_id="user-X" (who created none of the invoices) and min_amount=1000
        Expected Results:
        1. detected=True — namespace-wide sum $1200 exceeds min_amount $1000, even though
           user-X submitted no invoices

        Impact: In a multi-player namespace one active user can push the namespace total over
                the threshold and silently award the invoice-amount badge to every other player
                in that namespace. Challenge authors who expect per-user amount tracking will
                see badges firing unexpectedly.
        """
        _make_invoice(db, "ns-shared-amt", amount=600.0)
        _make_invoice(db, "ns-shared-amt", amount=600.0)

        evaluator = InvoiceAmountEvaluator("badge-test", config={"min_amount": 1000})
        result = await evaluator.check_event(_event("ns-shared-amt", "user-X"), db)
        assert result.detected is True, (
            "EVAL-IA-006: InvoiceAmountEvaluator sums namespace-level amounts "
            "without user_id scoping — any namespace member can trigger the badge"
        )


# ===========================================================================
# VendorCountEvaluator
# ===========================================================================


class TestVendorCountEvaluator:

    @pytest.mark.unit
    def test_eval_vc_001_config_requires_min_count(self):
        """EVAL-VC-001: VendorCountEvaluator raises ValueError when min_count missing

        Title: VendorCountEvaluator validates min_count in config
        Basically question: Does VendorCountEvaluator raise ValueError when
                            config has no min_count?
        Steps:
        1. Instantiate with empty config
        Expected Results:
        1. ValueError raised with "min_count is required"

        Impact: Misconfigured badge silently never awards.
        """
        with pytest.raises(ValueError, match="min_count is required"):
            VendorCountEvaluator("badge-test", config={})

    @pytest.mark.unit
    def test_eval_vc_002_invalid_vendor_status_rejected(self):
        """EVAL-VC-002: VendorCountEvaluator rejects invalid vendor_status

        Title: VendorCountEvaluator validates vendor_status in config
        Basically question: Does VendorCountEvaluator raise ValueError when
                            vendor_status is not in valid set?
        Steps:
        1. Instantiate with vendor_status="hacked"
        Expected Results:
        1. ValueError raised

        Impact: Invalid status filter silently matches nothing.
        """
        with pytest.raises(ValueError):
            VendorCountEvaluator("badge-test", config={"min_count": 1, "vendor_status": "hacked"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_vc_003_detected_when_count_met(self, db):
        """EVAL-VC-003: VendorCountEvaluator detects when vendor count >= min_count

        Title: VendorCountEvaluator returns detected=True when threshold met
        Basically question: Does VendorCountEvaluator count vendors in namespace
                            and detect when min_count is reached?
        Steps:
        1. Create 2 vendors in "ns-vendor"
        2. Instantiate with min_count=2
        3. Call check_event
        Expected Results:
        1. detected=True, confidence=1.0
        2. evidence["vendor_count"] == 2

        Impact: If detection fails, vendor onboarding badges never award.
        """
        _make_vendor(db, "ns-vendor")
        _make_vendor(db, "ns-vendor")

        evaluator = VendorCountEvaluator("badge-test", config={"min_count": 2})
        result = await evaluator.check_event(_event("ns-vendor"), db)

        assert result.detected is True
        assert result.evidence["vendor_count"] == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_vc_004_status_filter_applied(self, db):
        """EVAL-VC-004: VendorCountEvaluator filters by vendor_status

        Title: VendorCountEvaluator only counts vendors with matching status
        Basically question: Does vendor_status config exclude vendors whose
                            status does not match?
        Steps:
        1. Create 1 active vendor and 1 pending vendor in "ns-vstatus"
        2. Instantiate with min_count=1, vendor_status="active"
        3. Call check_event
        Expected Results:
        1. detected=True (1 active vendor == min_count=1)
        2. evidence["vendor_count"] == 1

        Impact: Without status filter, pending vendors count toward badges that
                should only trigger on approved/active vendors.
        """
        _make_vendor(db, "ns-vstatus", status="active")
        _make_vendor(db, "ns-vstatus", status="pending")

        evaluator = VendorCountEvaluator(
            "badge-test", config={"min_count": 1, "vendor_status": "active"}
        )
        result = await evaluator.check_event(_event("ns-vstatus"), db)

        assert result.detected is True
        assert result.evidence["vendor_count"] == 1

    @pytest.mark.unit
    def test_eval_vc_005_get_progress_returns_correct_fields(self, db):
        """EVAL-VC-005: VendorCountEvaluator.get_progress returns current/target/percentage

        Title: VendorCountEvaluator.get_progress returns correct progress data
        Basically question: Does get_progress compute percentage correctly?
        Steps:
        1. Create 1 vendor in "ns-vprog"
        2. Instantiate with min_count=4
        3. Call get_progress
        Expected Results:
        1. current == 1, target == 4, percentage == 25

        Impact: Wrong progress data misleads players.
        """
        _make_vendor(db, "ns-vprog")

        evaluator = VendorCountEvaluator("badge-test", config={"min_count": 4})
        progress = evaluator.get_progress("ns-vprog", "user-abc", db)

        assert progress["current"] == 1
        assert progress["target"] == 4
        assert progress["percentage"] == 25

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_vc_006_counts_all_namespace_vendors_regardless_of_user(self, db):
        """EVAL-VC-006: VendorCountEvaluator counts all vendors in the namespace, not just the current user's

        Title: VendorCountEvaluator does not filter by user_id — namespace-wide count
        Description: The evaluator counts every vendor in the namespace, regardless of which
                     user created them. In a shared namespace, vendors onboarded by any team
                     member count toward the badge. This test documents that behavior so it is
                     explicit and intentional rather than a hidden surprise.
        Basically question: Does VendorCountEvaluator count vendors created by other users
                            in the same namespace toward the badge threshold?
        Steps:
        1. Create 2 vendors in "ns-shared-v" (no user_id association on the Vendor model)
        2. Call check_event with user_id="user-B" and min_count=2
        Expected Results:
        1. detected=True — all namespace vendors are counted regardless of user_id

        Impact: Challenge authors should be aware that this evaluator operates at namespace
                scope. If per-user isolation is needed, use ChallengeCompletionEvaluator
                which does filter by user_id.
        """
        _make_vendor(db, "ns-shared-v")
        _make_vendor(db, "ns-shared-v")

        evaluator = VendorCountEvaluator("badge-test", config={"min_count": 2})
        result = await evaluator.check_event(_event("ns-shared-v", "user-B"), db)
        assert result.detected is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_vc_007_no_vendor_status_config_counts_all_statuses(self, db):
        """EVAL-VC-007: VendorCountEvaluator counts vendors of every status when vendor_status is not configured

        Title: Omitting vendor_status counts pending and inactive vendors — contradicts the documented default of "active"
        Description: The class docstring says the default status filter is "active". In practice,
                     when vendor_status is absent from the config, the code does
                     self.config.get("vendor_status") which returns None, and the if vendor_status:
                     guard skips the filter entirely. The query then counts vendors of all statuses
                     (pending, active, inactive). The documented default and the actual behavior
                     are contradictory.
        Basically question: Does VendorCountEvaluator count pending and inactive vendors when
                            no vendor_status is set in config, despite the docstring claiming the default is "active"?
        Steps:
        1. Create 1 vendor with status="pending" and 1 with status="inactive" in "ns-vendor-default"
        2. Create NO active vendors
        3. Instantiate with only min_count=2 (no vendor_status key)
        4. Call check_event
        Expected Results:
        1. detected=True — pending and inactive vendors are counted because vendor_status
           defaults to no filter, not "active" as the docstring claims

        Impact: A challenge author who reads the docstring and omits vendor_status expecting
                "active" filtering will instead get a badge that fires on pending or inactive
                vendors. Players can earn the badge with vendor records that were never approved,
                bypassing the intended game design.
        """
        _make_vendor(db, "ns-vendor-default", status="pending")
        _make_vendor(db, "ns-vendor-default", status="inactive")

        evaluator = VendorCountEvaluator("badge-test", config={"min_count": 2})
        result = await evaluator.check_event(_event("ns-vendor-default"), db)
        assert result.detected is True, (
            "EVAL-VC-007: omitting vendor_status should default to 'active' per docstring "
            "but actually counts all statuses — pending/inactive vendors satisfy the threshold"
        )


# ===========================================================================
# ChallengeCompletionEvaluator
# ===========================================================================


class TestChallengeCompletionEvaluator:

    @pytest.mark.unit
    def test_eval_cc_001_config_requires_min_count(self):
        """EVAL-CC-001: ChallengeCompletionEvaluator raises ValueError when min_count missing

        Title: ChallengeCompletionEvaluator validates min_count in config
        Basically question: Does ChallengeCompletionEvaluator raise ValueError
                            when config has no min_count?
        Steps:
        1. Instantiate with empty config
        Expected Results:
        1. ValueError raised with "min_count is required"

        Impact: Misconfigured completion badge silently never awards.
        """
        with pytest.raises(ValueError, match="min_count is required"):
            ChallengeCompletionEvaluator("badge-test", config={})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_cc_002_detected_when_completed_count_met(self, db):
        """EVAL-CC-002: ChallengeCompletionEvaluator detects when completed count >= min_count

        Title: ChallengeCompletionEvaluator returns detected=True when threshold met
        Basically question: Does ChallengeCompletionEvaluator count completed
                            challenges for a specific namespace+user_id and detect
                            when min_count is reached?
        Steps:
        1. Create 2 challenges and mark both completed for user-abc in ns-cc
        2. Instantiate with min_count=2
        3. Call check_event
        Expected Results:
        1. detected=True, confidence=1.0
        2. evidence["completed_count"] == 2

        Impact: If completion badge detection fails, the "completionist" badge
                never awards regardless of how many challenges are done.
        """
        _make_challenge(db, "chall-001")
        _make_challenge(db, "chall-002")
        _make_progress(db, "ns-cc", "user-abc", "chall-001")
        _make_progress(db, "ns-cc", "user-abc", "chall-002")

        evaluator = ChallengeCompletionEvaluator("badge-test", config={"min_count": 2})
        result = await evaluator.check_event(_event("ns-cc", "user-abc"), db)

        assert result.detected is True
        assert result.evidence["completed_count"] == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_cc_003_only_completed_status_counts(self, db):
        """EVAL-CC-003: ChallengeCompletionEvaluator only counts status="completed"

        Title: ChallengeCompletionEvaluator ignores non-completed progress entries
        Basically question: Does ChallengeCompletionEvaluator exclude challenges
                            with status != "completed" from the count?
        Steps:
        1. Create challenge with in_progress status and one with completed
        2. Instantiate with min_count=2
        3. Call check_event
        Expected Results:
        1. detected=False (only 1 completed, need 2)

        Impact: If in_progress counts, badges award prematurely before
                the player actually solves the challenge.
        """
        _make_challenge(db, "chall-inp")
        _make_challenge(db, "chall-done")
        _make_progress(db, "ns-cc2", "user-abc", "chall-inp", status="in_progress")
        _make_progress(db, "ns-cc2", "user-abc", "chall-done", status="completed")

        evaluator = ChallengeCompletionEvaluator("badge-test", config={"min_count": 2})
        result = await evaluator.check_event(_event("ns-cc2", "user-abc"), db)

        assert result.detected is False
        assert result.evidence["completed_count"] == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_cc_004_missing_user_id_not_detected(self, db):
        """EVAL-CC-004: ChallengeCompletionEvaluator returns not-detected for missing user_id

        Title: ChallengeCompletionEvaluator handles missing user_id in event
        Basically question: Does ChallengeCompletionEvaluator return detected=False
                            (not raise) when event has no user_id?
        Steps:
        1. Call check_event with event missing user_id
        Expected Results:
        1. detected=False, no exception

        Impact: Missing user_id would crash event pipeline if not handled gracefully.
        """
        evaluator = ChallengeCompletionEvaluator("badge-test", config={"min_count": 1})
        result = await evaluator.check_event({"namespace": "ns-test"}, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_cc_005_category_filter_applied(self, db):
        """EVAL-CC-005: ChallengeCompletionEvaluator filters by challenge_category

        Title: ChallengeCompletionEvaluator only counts challenges in specified category
        Basically question: Does challenge_category config limit counting to only
                            challenges in that category?
        Steps:
        1. Complete 1 "recon" challenge and 1 "injection" challenge
        2. Instantiate with min_count=1, challenge_category="recon"
        3. Call check_event
        Expected Results:
        1. detected=True (1 recon completed >= min_count=1)
        2. evidence["completed_count"] == 1

        Impact: Without category filter, completing any challenge awards
                category-specific badges — destroying challenge progression logic.
        """
        _make_challenge(db, "recon-001", category="recon")
        _make_challenge(db, "inject-001", category="injection")
        _make_progress(db, "ns-cat", "user-abc", "recon-001")
        _make_progress(db, "ns-cat", "user-abc", "inject-001")

        evaluator = ChallengeCompletionEvaluator(
            "badge-test", config={"min_count": 1, "challenge_category": "recon"}
        )
        result = await evaluator.check_event(_event("ns-cat", "user-abc"), db)

        assert result.detected is True
        assert result.evidence["completed_count"] == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eval_cc_006_user_isolation_enforced(self, db):
        """EVAL-CC-006: ChallengeCompletionEvaluator isolates progress by user_id

        Title: ChallengeCompletionEvaluator does not count other users' completions
        Basically question: Does ChallengeCompletionEvaluator use user_id to
                            scope the completed challenge count per player?
        Steps:
        1. Mark challenge completed for user-other in same namespace
        2. Call check_event for user-mine with min_count=1
        Expected Results:
        1. detected=False — user-mine has no completions despite namespace having one

        Impact: Without user_id isolation, completing a challenge as one user
                awards the badge to all users in the namespace.
        """
        _make_challenge(db, "shared-chall")
        _make_progress(db, "ns-shared", "user-other", "shared-chall")

        evaluator = ChallengeCompletionEvaluator("badge-test", config={"min_count": 1})
        result = await evaluator.check_event(_event("ns-shared", "user-mine"), db)

        assert result.detected is False
