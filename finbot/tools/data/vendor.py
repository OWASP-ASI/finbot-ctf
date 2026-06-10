"""Vendor data tools"""

import logging
from typing import Any

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import VendorRepository

logger = logging.getLogger(__name__)


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
    db = next(get_db())
    try:
        vendor_repo = VendorRepository(db, session_context)
        vendor = vendor_repo.get_vendor(vendor_id)
        if not vendor:
            raise ValueError("Vendor not found")
        return vendor.to_dict()
    finally:
        db.close()


async def get_vendor_contact_info(
    vendor_id: int,
    session_context: SessionContext,
) -> dict[str, Any]:
    """Get vendor contact information for communication purposes"""
    logger.info("Getting vendor contact info for vendor_id: %s", vendor_id)
    db = next(get_db())
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
    db = next(get_db())
    vendor_repo = VendorRepository(db, session_context)
    # append notes to the existing agent_notes
    vendor = vendor_repo.get_vendor(vendor_id)
    if not vendor:
        raise ValueError("Vendor not found")

    # capture previous state for events
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
    db = next(get_db())
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
