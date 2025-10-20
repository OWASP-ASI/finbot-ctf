"""Vendor Portal API Routes"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import VendorRepository

# Create API router
router = APIRouter(prefix="/api/v1", tags=["vendor-api"])


class VendorRegistrationRequest(BaseModel):
    """Vendor registration request model"""

    # Company Information
    company_name: str
    vendor_category: str
    industry: str
    services: str

    # Contact Information
    name: str
    email: str
    phone: str | None = None

    # Financial Information
    tin: str
    bank_account_number: str
    bank_name: str
    bank_routing_number: str
    bank_account_holder_name: str


@router.post("/vendors/register")
async def register_vendor(
    vendor_data: VendorRegistrationRequest,
    session_context: SessionContext = Depends(get_session_context),
):
    """Register a new vendor"""
    try:
        db = next(get_db())
        vendor_repo = VendorRepository(db, session_context)

        # Create vendor with all required fields
        vendor = vendor_repo.create_vendor(
            company_name=vendor_data.company_name,
            vendor_category=vendor_data.vendor_category,
            industry=vendor_data.industry,
            services=vendor_data.services,
            contact_name=vendor_data.name,
            email=vendor_data.email,
            tin=vendor_data.tin,
            bank_account_number=vendor_data.bank_account_number,
            bank_name=vendor_data.bank_name,
            bank_routing_number=vendor_data.bank_routing_number,
            bank_account_holder_name=vendor_data.bank_account_holder_name,
            phone=vendor_data.phone,
        )

        return {
            "success": True,
            "message": "Vendor registered successfully",
            "vendor_id": vendor.id,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to register vendor: {str(e)}"
        ) from e


@router.get("/vendors/me")
async def get_my_vendors(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get vendors for current user"""
    db = next(get_db())
    vendor_repo = VendorRepository(db, session_context)

    vendors = vendor_repo.list_vendors()

    return {
        "vendors": [
            {
                "id": vendor.id,
                "company_name": vendor.company_name,
                "email": vendor.email,
                "status": vendor.status,
                "vendor_category": vendor.vendor_category,
                "industry": vendor.industry,
                "created_at": vendor.created_at.isoformat(),
            }
            for vendor in vendors
        ]
    }


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(
    vendor_id: int, session_context: SessionContext = Depends(get_session_context)
):
    """Delete a vendor"""
    db = next(get_db())
    vendor_repo = VendorRepository(db, session_context)

    success = vendor_repo.delete_vendor(vendor_id)

    if not success:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return {"success": True, "message": "Vendor deleted successfully"}
