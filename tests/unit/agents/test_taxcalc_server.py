import pytest

from finbot.mcp.servers.taxcalc.server import verify_invoice_math_logic


def test_verify_invoice_math_accepts_consistent_invoice() -> None:
    result = verify_invoice_math_logic(
        line_items=[
            {
                "description": "Consulting services",
                "quantity": 10,
                "unit_price": 125.0,
                "line_total": 1250.0,
            },
            {
                "description": "Travel expenses",
                "quantity": 2,
                "unit_price": 75.0,
                "line_total": 150.0,
            },
        ],
        subtotal=1400.0,
        tax_amount=112.0,
        total_amount=1512.0,
    )

    assert result["valid"] is True
    assert result["computed_subtotal"] == 1400.0
    assert result["computed_total"] == 1512.0
    assert result["discrepancies"] == []


def test_verify_invoice_math_flags_line_item_mismatch() -> None:
    result = verify_invoice_math_logic(
        line_items=[
            {
                "description": "Platform license",
                "quantity": 3,
                "unit_price": 200.0,
                "line_total": 550.0,
            }
        ],
        subtotal=550.0,
        total_amount=550.0,
    )

    assert result["valid"] is False
    assert any(d["type"] == "line_total_mismatch" for d in result["discrepancies"])


def test_verify_invoice_math_flags_subtotal_and_total_mismatch() -> None:
    result = verify_invoice_math_logic(
        line_items=[
            {"description": "Review", "quantity": 4, "unit_price": 99.99},
            {"description": "Support", "quantity": 1, "unit_price": 50.0},
        ],
        subtotal=300.0,
        tax_amount=20.0,
        total_amount=320.0,
    )

    assert result["valid"] is False
    discrepancy_types = {d["type"] for d in result["discrepancies"]}
    assert "subtotal_mismatch" in discrepancy_types
    assert "total_mismatch" in discrepancy_types


@pytest.mark.parametrize(
    ("claimed_total", "tolerance", "expected_valid"),
    [
        (107.0, 0.01, True),
        (107.02, 0.01, False),
        (107.02, 0.03, True),
    ],
)
def test_verify_invoice_math_respects_tolerance(
    claimed_total: float, tolerance: float, expected_valid: bool
) -> None:
    result = verify_invoice_math_logic(
        line_items=[
            {"description": "Usage", "quantity": 2, "unit_price": 50.0},
        ],
        subtotal=100.0,
        tax_amount=7.0,
        total_amount=claimed_total,
        tolerance=tolerance,
    )

    assert result["valid"] is expected_valid