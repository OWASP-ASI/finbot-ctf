"""Vendor data tools"""

import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import VendorRepository

logger = logging.getLogger(__name__)

VALID_VENDOR_STATUSES = {"pending", "active", "inactive"}
VALID_TRUST_LEVELS = {"low", "standard", "high"}
VALID_RISK_LEVELS = {"low", "medium", "high"}


async def get_vendor_details(
    vendor_id: int, session_context: SessionContext
) -> dict[str, Any]:
    """Get the details of the vendor

    Args:
        vendor_id: The ID of the vendor to retrieve
        session_context: The session context

    Returns:
        Dictionary containing vendor details
    """
    logger.info("Getting vendor details for vendor_id: %s", vendor_id)
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")
        return vendor.to_dict()


async def get_vendor_contact_info(
    vendor_id: int,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Get vendor contact information for communication purposes"""
    logger.info("Getting vendor contact info for vendor_id: %s", vendor_id)
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")

        return {
            "vendor_id": vendor.id,
            "company_name": vendor.company_name,
            "contact_name": vendor.contact_name,
            "email": vendor.email,
            "phone": vendor.phone,
            "status": vendor.status,
        }


async def update_vendor_status(
    vendor_id: int,
    status: str,
    trust_level: str,
    risk_level: str,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Update the status, trust level, risk level of the vendor"""
    logger.info(
        "Updating vendor status for vendor_id: %s to status: %s, trust level: %s, risk level: %s. Agent notes: %s",
        vendor_id,
        status,
        trust_level,
        risk_level,
        agent_notes,
    )
    if status is None or not isinstance(status, str) or status.strip() == "":
        raise ValueError(
            f"Invalid status: {status!r}. Must be one of {VALID_VENDOR_STATUSES}"
        )
    if status not in VALID_VENDOR_STATUSES:
        raise ValueError(
            f"Invalid status: {status!r}. Must be one of {VALID_VENDOR_STATUSES}"
        )

    if trust_level is None or not isinstance(trust_level, str) or trust_level.strip() == "":
        raise ValueError(
            f"Invalid trust_level: {trust_level!r}. Must be one of {VALID_TRUST_LEVELS}"
        )
    if trust_level not in VALID_TRUST_LEVELS:
        raise ValueError(
            f"Invalid trust_level: {trust_level!r}. Must be one of {VALID_TRUST_LEVELS}"
        )

    if risk_level is None or not isinstance(risk_level, str) or risk_level.strip() == "":
        raise ValueError(
            f"Invalid risk_level: {risk_level!r}. Must be one of {VALID_RISK_LEVELS}"
        )
    if risk_level not in VALID_RISK_LEVELS:
        raise ValueError(
            f"Invalid risk_level: {risk_level!r}. Must be one of {VALID_RISK_LEVELS}"
        )

    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")

        previous_state = {
            "status": vendor.status,
            "trust_level": vendor.trust_level,
            "risk_level": vendor.risk_level,
        }

        existing_notes = vendor.agent_notes or ""
        new_notes = f"{existing_notes}\n\n{agent_notes}"
        vendor = vendor_repo.update_vendor(
            vendor_id,
            status=status,
            trust_level=trust_level,
            risk_level=risk_level,
            agent_notes=new_notes,
        )
        if not vendor:
            raise ValueError("Vendor not found")
        result = vendor.to_dict()
        result["_previous_state"] = previous_state
        return result


async def update_vendor_agent_notes(
    vendor_id: int,
    agent_notes: str,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Update the agent notes of the vendor"""
    logger.info(
        "Updating vendor agent notes for vendor_id: %s. Agent notes: %s",
        vendor_id,
        agent_notes,
    )
    with db_session() as db:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")
        existing_notes = vendor.agent_notes or ""
        new_notes = f"{existing_notes}\n\n{agent_notes}"
        vendor = vendor_repo.update_vendor(
            vendor_id,
            agent_notes=new_notes,
        )
        if not vendor:
            raise ValueError("Vendor not found")
        return vendor.to_dict()
