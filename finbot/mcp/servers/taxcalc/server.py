"""TaxCalc MCP Server -- mock tax calculator.

Exposes tax calculation, invoice arithmetic verification, rate lookup, and TIN
validation tools via MCP protocol. Pure computation -- no DB writes. Rates are
configurable via MCPServerConfig.
"""

import logging
import re
from typing import Any

from fastmcp import FastMCP

from finbot.core.auth.session import SessionContext

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "default_jurisdiction": "US-CA",
    "tax_rates": {
        "US-CA": {"state": 7.25, "county": 1.0, "city": 0.0, "label": "California"},
        "US-NY": {"state": 8.0, "county": 0.5, "city": 4.5, "label": "New York"},
        "US-TX": {"state": 6.25, "county": 0.0, "city": 0.0, "label": "Texas"},
        "US-FL": {"state": 6.0, "county": 0.5, "city": 0.0, "label": "Florida"},
        "US-WA": {"state": 6.5, "county": 0.3, "city": 0.0, "label": "Washington"},
        "US-NV": {"state": 6.85, "county": 1.25, "city": 0.0, "label": "Nevada"},
        "US-IL": {"state": 6.25, "county": 1.75, "city": 1.25, "label": "Illinois"},
    },
    "service_tax_exempt": True,
    "entertainment_surcharge_pct": 2.5,
}


def _round_currency(value: float) -> float:
    """Round a currency value to two decimal places."""
    return round(float(value), 2)


def verify_invoice_math_logic(
    line_items: list[dict[str, Any]],
    subtotal: float | None = None,
    tax_amount: float | None = None,
    total_amount: float | None = None,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Verify invoice arithmetic for line items and aggregate totals.

    Each line item should contain at minimum:
    - description: optional label for the item
    - quantity: numeric quantity
    - unit_price: numeric unit price
    - line_total: optional claimed total for the line
    """
    discrepancies: list[dict[str, Any]] = []
    computed_subtotal = 0.0

    for index, item in enumerate(line_items):
        quantity = float(item.get("quantity", 0))
        unit_price = float(item.get("unit_price", 0))
        computed_line_total = _round_currency(quantity * unit_price)
        computed_subtotal += computed_line_total

        claimed_line_total = item.get("line_total")
        if claimed_line_total is not None:
            claimed_line_total = _round_currency(float(claimed_line_total))
            if abs(computed_line_total - claimed_line_total) > tolerance:
                discrepancies.append(
                    {
                        "type": "line_total_mismatch",
                        "line_index": index,
                        "description": item.get("description") or f"Line {index + 1}",
                        "expected": computed_line_total,
                        "actual": claimed_line_total,
                    }
                )

    computed_subtotal = _round_currency(computed_subtotal)
    computed_tax = _round_currency(float(tax_amount or 0.0))
    computed_total = _round_currency(computed_subtotal + computed_tax)

    if subtotal is not None:
        claimed_subtotal = _round_currency(float(subtotal))
        if abs(computed_subtotal - claimed_subtotal) > tolerance:
            discrepancies.append(
                {
                    "type": "subtotal_mismatch",
                    "expected": computed_subtotal,
                    "actual": claimed_subtotal,
                }
            )

    if total_amount is not None:
        claimed_total = _round_currency(float(total_amount))
        if abs(computed_total - claimed_total) > tolerance:
            discrepancies.append(
                {
                    "type": "total_mismatch",
                    "expected": computed_total,
                    "actual": claimed_total,
                }
            )

    return {
        "valid": len(discrepancies) == 0,
        "computed_subtotal": computed_subtotal,
        "computed_tax": computed_tax,
        "computed_total": computed_total,
        "line_item_count": len(line_items),
        "discrepancies": discrepancies,
    }


def create_taxcalc_server(
    session_context: SessionContext,
    server_config: dict[str, Any] | None = None,
) -> FastMCP:
    """Create a TaxCalc MCP server instance."""
    config = {**DEFAULT_CONFIG, **(server_config or {})}
    mcp = FastMCP("TaxCalc")

    @mcp.tool
    def calculate_tax(
        amount: float,
        jurisdiction: str = "",
        category: str = "goods",
    ) -> dict[str, Any]:
        """Calculate tax for a given amount based on jurisdiction and category.

        Returns a breakdown of applicable taxes and the total amount including tax.
        Categories: 'goods' (standard tax), 'services' (may be exempt), 'entertainment' (surcharge applies).
        """
        jurisdiction = jurisdiction or config.get("default_jurisdiction", "US-CA")
        tax_rates = config.get("tax_rates", DEFAULT_CONFIG["tax_rates"])
        rates = tax_rates.get(jurisdiction)

        if not rates:
            return {
                "error": f"Unknown jurisdiction: {jurisdiction}",
                "available_jurisdictions": list(tax_rates.keys()),
            }

        if category == "services" and config.get("service_tax_exempt", True):
            return {
                "amount": amount,
                "jurisdiction": jurisdiction,
                "category": category,
                "tax_exempt": True,
                "tax_amount": 0.0,
                "total_amount": amount,
                "breakdown": {"note": "Services are tax-exempt in this jurisdiction"},
            }

        state_tax = amount * (rates["state"] / 100)
        county_tax = amount * (rates["county"] / 100)
        city_tax = amount * (rates["city"] / 100)
        subtotal_tax = state_tax + county_tax + city_tax

        surcharge = 0.0
        if category == "entertainment":
            surcharge_pct = config.get("entertainment_surcharge_pct", 2.5)
            surcharge = amount * (surcharge_pct / 100)

        total_tax = subtotal_tax + surcharge

        return {
            "amount": amount,
            "jurisdiction": jurisdiction,
            "jurisdiction_label": rates.get("label", jurisdiction),
            "category": category,
            "tax_exempt": False,
            "breakdown": {
                "state_tax": round(state_tax, 2),
                "state_rate": rates["state"],
                "county_tax": round(county_tax, 2),
                "county_rate": rates["county"],
                "city_tax": round(city_tax, 2),
                "city_rate": rates["city"],
                "entertainment_surcharge": round(surcharge, 2) if surcharge else None,
            },
            "tax_amount": round(total_tax, 2),
            "total_amount": round(amount + total_tax, 2),
        }

    @mcp.tool
    def verify_invoice_math(
        line_items: list[dict[str, Any]],
        subtotal: float | None = None,
        tax_amount: float | None = None,
        total_amount: float | None = None,
        tolerance: float = 0.01,
    ) -> dict[str, Any]:
        """Verify invoice arithmetic for line items, subtotal, tax, and total.

        Use this to confirm that an invoice's math is internally consistent before
        approving or escalating it. The tool returns computed totals and a list of
        any mismatches it detects.
        """
        return verify_invoice_math_logic(
            line_items=line_items,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            tolerance=tolerance,
        )

    @mcp.tool
    def get_tax_rates(jurisdiction: str = "") -> dict[str, Any]:
        """Get applicable tax rates for a jurisdiction.

        Returns all tax rate components (state, county, city) and any special surcharges.
        If no jurisdiction is specified, returns rates for all available jurisdictions.
        """
        tax_rates = config.get("tax_rates", DEFAULT_CONFIG["tax_rates"])

        if not jurisdiction:
            return {
                "default_jurisdiction": config.get("default_jurisdiction", "US-CA"),
                "jurisdictions": {
                    code: {
                        "label": rates.get("label", code),
                        "combined_rate": rates["state"] + rates["county"] + rates["city"],
                        **rates,
                    }
                    for code, rates in tax_rates.items()
                },
                "service_tax_exempt": config.get("service_tax_exempt", True),
                "entertainment_surcharge_pct": config.get("entertainment_surcharge_pct", 2.5),
            }

        rates = tax_rates.get(jurisdiction)
        if not rates:
            return {
                "error": f"Unknown jurisdiction: {jurisdiction}",
                "available_jurisdictions": list(tax_rates.keys()),
            }

        return {
            "jurisdiction": jurisdiction,
            "label": rates.get("label", jurisdiction),
            "state_rate": rates["state"],
            "county_rate": rates["county"],
            "city_rate": rates["city"],
            "combined_rate": rates["state"] + rates["county"] + rates["city"],
            "service_tax_exempt": config.get("service_tax_exempt", True),
            "entertainment_surcharge_pct": config.get("entertainment_surcharge_pct", 2.5),
        }

    @mcp.tool
    def validate_tax_id(tax_id: str, country: str = "US") -> dict[str, Any]:
        """Validate a tax identification number (TIN/EIN) format.

        Checks if the provided tax ID matches expected formats for the given country.
        Note: This validates format only, not whether the ID is registered with tax authorities.
        """
        tax_id_clean = re.sub(r"[\s\-]", "", tax_id)

        if country == "US":
            # EIN format: XX-XXXXXXX (9 digits)
            if re.match(r"^\d{9}$", tax_id_clean):
                return {
                    "tax_id": tax_id,
                    "country": country,
                    "format_valid": True,
                    "id_type": "EIN",
                    "formatted": f"{tax_id_clean[:2]}-{tax_id_clean[2:]}",
                }
            # SSN format: XXX-XX-XXXX (9 digits, different grouping)
            if re.match(r"^\d{9}$", tax_id_clean) and tax_id_clean[:3] != "00":
                return {
                    "tax_id": tax_id,
                    "country": country,
                    "format_valid": True,
                    "id_type": "SSN",
                    "formatted": f"{tax_id_clean[:3]}-{tax_id_clean[3:5]}-{tax_id_clean[5:]}",
                }
            return {
                "tax_id": tax_id,
                "country": country,
                "format_valid": False,
                "error": "US tax IDs must be 9 digits (EIN: XX-XXXXXXX)",
            }

        return {
            "tax_id": tax_id,
            "country": country,
            "format_valid": False,
            "error": f"Tax ID validation not supported for country: {country}",
        }

    return mcp
