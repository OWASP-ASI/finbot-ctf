"""FinStripe repositories -- data access for payment transactions."""

from datetime import UTC, datetime

from finbot.core.data.repositories import NamespacedRepository
from finbot.mcp.servers.finstripe.models import PaymentTransaction


class PaymentTransactionRepository(NamespacedRepository):
    """Repository for PaymentTransaction -- tracks FinStripe fund transfers."""

    def create_transaction(
        self,
        invoice_id: int,
        vendor_id: int,
        transfer_id: str,
        amount: float,
        payment_method: str,
        currency: str = "usd",
        status: str = "pending",
        description: str | None = None,
        metadata_json: str | None = None,
    ) -> PaymentTransaction:
        txn = PaymentTransaction(
            namespace=self.namespace,
            invoice_id=invoice_id,
            vendor_id=vendor_id,
            transfer_id=transfer_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            status=status,
            description=description,
            metadata_json=metadata_json,
        )
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)
        return txn

    def get_by_transfer_id(self, transfer_id: str) -> PaymentTransaction | None:
        return (
            self._add_namespace_filter(
                self.db.query(PaymentTransaction), PaymentTransaction
            )
            .filter(PaymentTransaction.transfer_id == transfer_id)
            .first()
        )

    def list_for_vendor(
        self,
        vendor_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PaymentTransaction]:
        if limit < 0:
            raise ValueError("limit must be zero or a positive integer")
        if offset < 0:
            raise ValueError("offset must be zero or a positive integer")
        return (
            self._add_namespace_filter(
                self.db.query(PaymentTransaction), PaymentTransaction
            )
            .filter(PaymentTransaction.vendor_id == vendor_id)
            .order_by(PaymentTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_for_invoice(self, invoice_id: int) -> list[PaymentTransaction]:
        return (
            self._add_namespace_filter(
                self.db.query(PaymentTransaction), PaymentTransaction
            )
            .filter(PaymentTransaction.invoice_id == invoice_id)
            .order_by(PaymentTransaction.created_at.desc())
            .all()
        )

    def update_status(
        self, transfer_id: str, status: str
    ) -> PaymentTransaction | None:
        txn = self.get_by_transfer_id(transfer_id)
        if txn:
            txn.status = status
            txn.updated_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(txn)
        return txn
