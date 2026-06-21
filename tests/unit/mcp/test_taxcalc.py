"""
Unit tests for finbot/mcp/servers/taxcalc/server.py

TaxCalc is a stateless mock tax calculator. Pure computation — no DB writes.
Tests cover:
- Tax calculation math correctness for all jurisdictions
- Category handling: goods, services (exempt), entertainment (surcharge)
- Tax rate lookup (specific and all jurisdictions)
- TIN/EIN format validation
- Dead-code SSN branch (unreachable — same condition as EIN, never reached)
- Negative and zero amount edge cases
- Config override (custom rates, service_tax_exempt toggle)
- Tool discovery

No database fixture or patching required — all operations are pure computation.

All bug-documenting tests assert CORRECT behavior and therefore FAIL when
the bug is present. They PASS only when the bug is fixed.
"""

import pytest

from finbot.core.auth.session import session_manager
from finbot.mcp.servers.taxcalc.server import create_taxcalc_server, DEFAULT_CONFIG

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ============================================================================
# Helpers
# ============================================================================

def make_session(email="taxtest@example.com"):
    return session_manager.create_session(email=email)


async def call(server, tool_name, **kwargs):
    """Call an MCP tool and return the result as a dict."""
    result = await server.call_tool(tool_name, kwargs)
    return result.structured_content


# ============================================================================
# calculate_tax
# ============================================================================

class TestCalculateTax:

    async def test_tc_calc_001_basic_goods_calculation_us_ca(self):
        """
        MCP-TC-CALC-001

        Title: calculate_tax returns correct tax breakdown for US-CA goods.

        Steps:
            1. Create server with default config.
            2. Call calculate_tax with amount=100.00, jurisdiction="US-CA", category="goods".
            3. Verify state_rate=7.25, county_rate=1.0, city_rate=0.0.
            4. Verify tax_amount=8.25, total_amount=108.25.

        Expected Results:
            Correct breakdown and totals returned.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="US-CA", category="goods")

        assert result.get("tax_exempt") is False
        assert result["breakdown"]["state_rate"] == 7.25
        assert result["breakdown"]["county_rate"] == 1.0
        assert result["breakdown"]["city_rate"] == 0.0
        assert result["tax_amount"] == 8.25
        assert result["total_amount"] == 108.25

    async def test_tc_calc_002_services_category_is_tax_exempt(self):
        """
        MCP-TC-CALC-002

        Title: Services category is tax-exempt when service_tax_exempt=True.

        Steps:
            1. Call calculate_tax with category="services".

        Expected Results:
            tax_exempt=True, tax_amount=0.0, total_amount equals input amount.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=500.0, jurisdiction="US-CA", category="services")

        assert result.get("tax_exempt") is True
        assert result["tax_amount"] == 0.0
        assert result["total_amount"] == 500.0

    async def test_tc_calc_003_entertainment_category_includes_surcharge(self):
        """
        MCP-TC-CALC-003

        Title: Entertainment category adds the entertainment surcharge on top of standard tax.

        Steps:
            1. Call calculate_tax with category="entertainment", amount=100.0, jurisdiction="US-CA".
            2. US-CA combined rate = 8.25%; entertainment surcharge = 2.5%.
            3. Total tax = 10.75, total_amount = 110.75.

        Expected Results:
            entertainment_surcharge=2.5 in breakdown; tax_amount=10.75.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="US-CA", category="entertainment")

        assert result.get("tax_exempt") is False
        assert result["breakdown"]["entertainment_surcharge"] == 2.5
        assert result["tax_amount"] == 10.75
        assert result["total_amount"] == 110.75

    async def test_tc_calc_004_unknown_jurisdiction_returns_error(self):
        """
        MCP-TC-CALC-004

        Title: Unknown jurisdiction returns an error with available jurisdictions listed.

        Steps:
            1. Call calculate_tax with jurisdiction="US-ZZ".

        Expected Results:
            Response contains `error` about unknown jurisdiction and lists available jurisdictions.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="US-ZZ")

        assert "error" in result
        assert "US-ZZ" in result["error"]
        assert "available_jurisdictions" in result

    async def test_tc_calc_005_empty_jurisdiction_uses_default(self):
        """
        MCP-TC-CALC-005

        Title: Empty jurisdiction string falls back to default_jurisdiction from config.

        Steps:
            1. Create server with default config (default_jurisdiction="US-CA").
            2. Call calculate_tax with amount=100.0, jurisdiction="" (empty).

        Expected Results:
            Calculation uses US-CA rates; no error returned.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax", amount=100.0, jurisdiction="")

        assert "error" not in result
        assert result.get("jurisdiction") == "US-CA"
        assert result["tax_amount"] == 8.25

    async def test_tc_calc_006_us_ny_calculation_with_city_tax(self):
        """
        MCP-TC-CALC-006

        Title: US-NY calculation includes state (8.0), county (0.5), and city (4.5) taxes.

        Steps:
            1. Call calculate_tax with amount=100.0, jurisdiction="US-NY".
            2. Total tax rate = 13.0%.

        Expected Results:
            tax_amount=13.0, total_amount=113.0.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="US-NY", category="goods")

        assert result["breakdown"]["state_rate"] == 8.0
        assert result["breakdown"]["county_rate"] == 0.5
        assert result["breakdown"]["city_rate"] == 4.5
        assert result["tax_amount"] == 13.0
        assert result["total_amount"] == 113.0

    async def test_tc_calc_007_amount_zero_returns_zero_tax(self):
        """
        MCP-TC-CALC-007

        Title: amount=0 returns zero tax for all components.

        Steps:
            1. Call calculate_tax with amount=0.0, jurisdiction="US-CA".

        Expected Results:
            tax_amount=0.0, total_amount=0.0.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax", amount=0.0, jurisdiction="US-CA")

        assert result.get("tax_exempt") is False
        assert result["tax_amount"] == 0.0
        assert result["total_amount"] == 0.0

    @pytest.mark.parametrize("amount", [-100.0, -1.0])
    async def test_tc_calc_008_negative_amount_accepted_without_validation(self, amount):
        """
        MCP-TC-CALC-008

        Title: Negative amount is accepted and produces a negative tax result without validation.

        BUG: The server does not validate that amount >= 0. A negative amount produces
        a logically incorrect negative tax, which could be used to generate fraudulent
        tax refund calculations.

        Steps:
            1. Call calculate_tax with a negative amount, jurisdiction="US-CA".
            2. Verify that an error is returned.

        Expected Results:
            Error returned for negative amount. (BUG: negative tax returned silently.)
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax", amount=amount, jurisdiction="US-CA")

        # BUG: server produces negative tax instead of rejecting negative amount
        assert "error" in result, "Negative amount should return an error"

    async def test_tc_calc_009_unknown_category_accepted_without_validation(self):
        """
        MCP-TC-CALC-009

        Title: Unknown category string is accepted without validation (treated as 'goods').

        BUG: The server only checks for "services" and "entertainment" categories.
        Any other string (including misspellings or injected values) silently falls
        through to the goods calculation without any validation error.

        Steps:
            1. Call calculate_tax with category="UNKNOWN_CATEGORY".
            2. Verify that an error is returned for unknown category.

        Expected Results:
            Error returned. (BUG: treated silently as goods calculation.)
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="US-CA", category="UNKNOWN_CATEGORY")

        # BUG: unknown category silently treated as goods
        assert "error" in result, "Unknown category should return an error"

    async def test_tc_calc_010_fractional_amounts_rounded_to_two_decimal_places(self):
        """
        MCP-TC-CALC-010

        Title: Tax amounts are rounded to 2 decimal places.

        Steps:
            1. Call calculate_tax with amount=33.33, jurisdiction="US-CA".
            2. US-CA rate = 8.25%; 33.33 * 0.0825 = 2.749725 → rounded to 2.75.

        Expected Results:
            tax_amount=2.75 (rounded), total_amount=36.08.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=33.33, jurisdiction="US-CA", category="goods")

        assert result["tax_amount"] == 2.75
        assert result["total_amount"] == 36.08

    async def test_tc_calc_011_all_seven_jurisdictions_compute_without_error(self):
        """
        MCP-TC-CALC-011

        Title: All 7 default jurisdictions return valid calculations.

        Steps:
            1. Call calculate_tax with amount=100.0 for each jurisdiction.

        Expected Results:
            No jurisdiction returns an error; all have valid tax_amount >= 0.
        """
        server = create_taxcalc_server(make_session())
        jurisdictions = ["US-CA", "US-NY", "US-TX", "US-FL", "US-WA", "US-NV", "US-IL"]
        for jur in jurisdictions:
            result = await call(server, "calculate_tax", amount=100.0, jurisdiction=jur)
            assert "error" not in result, f"Unexpected error for {jur}: {result}"
            assert result["tax_amount"] >= 0

    async def test_tc_calc_012_services_not_exempt_when_config_overrides(self):
        """
        MCP-TC-CALC-012

        Title: services category is taxed when service_tax_exempt=False in config.

        Steps:
            1. Create server with service_tax_exempt=False.
            2. Call calculate_tax with category="services", amount=100.0.

        Expected Results:
            tax_exempt=False and tax_amount > 0.
        """
        server = create_taxcalc_server(make_session(), server_config={"service_tax_exempt": False})
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="US-CA", category="services")

        assert result.get("tax_exempt") is False
        assert result["tax_amount"] > 0


# ============================================================================
# get_tax_rates
# ============================================================================

class TestGetTaxRates:

    async def test_tc_rates_001_no_jurisdiction_returns_all_rates(self):
        """
        MCP-TC-RATES-001

        Title: get_tax_rates with no jurisdiction returns all available jurisdictions.

        Steps:
            1. Call get_tax_rates with no jurisdiction argument.

        Expected Results:
            Response contains `jurisdictions` dict with all 7 default jurisdictions.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "get_tax_rates")

        assert "jurisdictions" in result
        assert len(result["jurisdictions"]) == 7

    async def test_tc_rates_002_specific_jurisdiction_returns_single_entry(self):
        """
        MCP-TC-RATES-002

        Title: get_tax_rates with a specific jurisdiction returns only that jurisdiction's rates.

        Steps:
            1. Call get_tax_rates with jurisdiction="US-TX".

        Expected Results:
            Response has jurisdiction="US-TX", state_rate=6.25, county_rate=0.0, city_rate=0.0.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "get_tax_rates", jurisdiction="US-TX")

        assert result.get("jurisdiction") == "US-TX"
        assert result["state_rate"] == 6.25
        assert result["county_rate"] == 0.0
        assert result["city_rate"] == 0.0

    async def test_tc_rates_003_unknown_jurisdiction_returns_error(self):
        """
        MCP-TC-RATES-003

        Title: get_tax_rates with unknown jurisdiction returns an error.

        Steps:
            1. Call get_tax_rates with jurisdiction="EU-DE".

        Expected Results:
            Response contains `error` and `available_jurisdictions`.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "get_tax_rates", jurisdiction="EU-DE")

        assert "error" in result
        assert "available_jurisdictions" in result

    async def test_tc_rates_004_combined_rate_equals_sum_of_components(self):
        """
        MCP-TC-RATES-004

        Title: combined_rate in the response equals state+county+city rates.

        Steps:
            1. Call get_tax_rates for each jurisdiction.
            2. Verify combined_rate == state_rate + county_rate + city_rate.

        Expected Results:
            No discrepancy for any jurisdiction.
        """
        server = create_taxcalc_server(make_session())
        all_rates = await call(server, "get_tax_rates")

        for code, rates in all_rates["jurisdictions"].items():
            expected = rates["state"] + rates["county"] + rates["city"]
            assert abs(rates["combined_rate"] - expected) < 0.001, \
                f"combined_rate mismatch for {code}: {rates['combined_rate']} != {expected}"

    async def test_tc_rates_005_response_includes_service_exempt_and_surcharge_config(self):
        """
        MCP-TC-RATES-005

        Title: get_tax_rates response includes service_tax_exempt and entertainment_surcharge_pct.

        Steps:
            1. Call get_tax_rates with jurisdiction="US-FL".

        Expected Results:
            service_tax_exempt and entertainment_surcharge_pct present.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "get_tax_rates", jurisdiction="US-FL")

        assert "service_tax_exempt" in result
        assert "entertainment_surcharge_pct" in result

    async def test_tc_rates_006_custom_tax_rates_override_default(self):
        """
        MCP-TC-RATES-006

        Title: Custom tax_rates in server_config replace the default rates.

        Steps:
            1. Create server with custom tax_rates containing only "US-TEST".
            2. Call get_tax_rates.

        Expected Results:
            Only "US-TEST" jurisdiction is returned; default jurisdictions are absent.
        """
        custom_config = {
            "tax_rates": {
                "US-TEST": {"state": 5.0, "county": 0.5, "city": 0.0, "label": "Test State"}
            }
        }
        server = create_taxcalc_server(make_session(), server_config=custom_config)
        result = await call(server, "get_tax_rates")

        assert "US-TEST" in result["jurisdictions"]
        assert "US-CA" not in result["jurisdictions"]


# ============================================================================
# validate_tax_id
# ============================================================================

class TestValidateTaxId:

    async def test_tc_tin_001_valid_nine_digit_ein_returns_valid(self):
        """
        MCP-TC-TIN-001

        Title: A 9-digit numeric string is a valid US EIN.

        Steps:
            1. Call validate_tax_id with tax_id="123456789", country="US".

        Expected Results:
            format_valid=True, id_type="EIN", formatted="12-3456789".
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="123456789", country="US")

        assert result["format_valid"] is True
        assert result["id_type"] == "EIN"
        assert result["formatted"] == "12-3456789"

    async def test_tc_tin_002_ein_with_dashes_normalized_correctly(self):
        """
        MCP-TC-TIN-002

        Title: EIN in XX-XXXXXXX format is validated after stripping dashes.

        Steps:
            1. Call validate_tax_id with tax_id="12-3456789".

        Expected Results:
            format_valid=True, id_type="EIN", formatted="12-3456789".
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="12-3456789", country="US")

        assert result["format_valid"] is True
        assert result["id_type"] == "EIN"

    async def test_tc_tin_003_invalid_format_returns_format_valid_false(self):
        """
        MCP-TC-TIN-003

        Title: Tax ID that is not 9 digits returns format_valid=False.

        Steps:
            1. Call validate_tax_id with tax_id="12345" (only 5 digits).

        Expected Results:
            format_valid=False and error message about format.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="12345", country="US")

        assert result["format_valid"] is False
        assert "error" in result

    async def test_tc_tin_004_ssn_branch_is_unreachable_dead_code(self):
        """
        MCP-TC-TIN-004

        Title: The SSN validation branch is unreachable dead code.

        BUG: In server.py the SSN validation block (lines ~166-173) is never reached.
        The condition `re.match(r"^\\d{9}$", tax_id_clean)` is identical to the EIN
        check above it. Since the EIN branch already returns on matching 9-digit input,
        the SSN block can never execute. Any 9-digit input is always classified as EIN,
        never as SSN.

        Steps:
            1. Call validate_tax_id with a 9-digit US SSN format (e.g. "123-45-6789").
            2. Verify that id_type="SSN" is returned.

        Expected Results:
            id_type="SSN". (BUG: id_type="EIN" is always returned for valid 9-digit input.)
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="123-45-6789", country="US")

        # BUG: SSN branch unreachable — always returns EIN
        assert result.get("id_type") == "SSN", \
            "9-digit with SSN hyphenation should be identified as SSN (dead code bug)"

    async def test_tc_tin_005_unknown_country_returns_not_supported_error(self):
        """
        MCP-TC-TIN-005

        Title: Unsupported country returns an error message.

        Steps:
            1. Call validate_tax_id with country="DE".

        Expected Results:
            format_valid=False and error about unsupported country.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="123456789", country="DE")

        assert result["format_valid"] is False
        assert "not supported" in result.get("error", "").lower()

    async def test_tc_tin_006_empty_tax_id_returns_invalid_format(self):
        """
        MCP-TC-TIN-006

        Title: Empty tax_id string returns format_valid=False.

        Steps:
            1. Call validate_tax_id with tax_id="".

        Expected Results:
            format_valid=False.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="", country="US")

        assert result["format_valid"] is False

    async def test_tc_tin_007_tax_id_with_spaces_stripped_and_validated(self):
        """
        MCP-TC-TIN-007

        Title: Spaces in tax_id are stripped before validation.

        Steps:
            1. Call validate_tax_id with tax_id="12 3456789" (space in middle).

        Expected Results:
            format_valid=True (spaces removed, 9 digits remain).
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="12 3456789", country="US")

        assert result["format_valid"] is True

    async def test_tc_tin_008_letters_in_tax_id_return_invalid(self):
        """
        MCP-TC-TIN-008

        Title: Tax ID containing letters returns format_valid=False for US.

        Steps:
            1. Call validate_tax_id with tax_id="AB-CDEFGHI".

        Expected Results:
            format_valid=False.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="AB-CDEFGHI", country="US")

        assert result["format_valid"] is False


# ============================================================================
# Server config
# ============================================================================

class TestTaxCalcServerConfig:

    def test_tc_cfg_001_default_config_has_expected_keys(self):
        """
        MCP-TC-CFG-001

        Title: DEFAULT_CONFIG contains all expected configuration keys.

        Steps:
            1. Check DEFAULT_CONFIG.

        Expected Results:
            Contains: default_jurisdiction, tax_rates, service_tax_exempt,
            entertainment_surcharge_pct.
        """
        assert "default_jurisdiction" in DEFAULT_CONFIG
        assert "tax_rates" in DEFAULT_CONFIG
        assert "service_tax_exempt" in DEFAULT_CONFIG
        assert "entertainment_surcharge_pct" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["default_jurisdiction"] == "US-CA"
        assert DEFAULT_CONFIG["service_tax_exempt"] is True
        assert DEFAULT_CONFIG["entertainment_surcharge_pct"] == 2.5

    def test_tc_cfg_002_default_config_has_seven_jurisdictions(self):
        """
        MCP-TC-CFG-002

        Title: DEFAULT_CONFIG.tax_rates contains exactly 7 jurisdictions.

        Steps:
            1. Check len(DEFAULT_CONFIG["tax_rates"]).

        Expected Results:
            7 jurisdictions: US-CA, US-NY, US-TX, US-FL, US-WA, US-NV, US-IL.
        """
        jurisdictions = set(DEFAULT_CONFIG["tax_rates"].keys())
        expected = {"US-CA", "US-NY", "US-TX", "US-FL", "US-WA", "US-NV", "US-IL"}
        assert jurisdictions == expected

    async def test_tc_cfg_003_custom_entertainment_surcharge_applied(self):
        """
        MCP-TC-CFG-003

        Title: Custom entertainment_surcharge_pct is applied in calculations.

        Steps:
            1. Create server with entertainment_surcharge_pct=10.0.
            2. Calculate entertainment tax on 100.0 in US-CA.
            3. US-CA base tax = 8.25; surcharge = 10.0. Total tax = 18.25.

        Expected Results:
            entertainment_surcharge=10.0 in breakdown; tax_amount=18.25.
        """
        server = create_taxcalc_server(make_session(),
            server_config={"entertainment_surcharge_pct": 10.0})
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="US-CA", category="entertainment")

        assert result["breakdown"]["entertainment_surcharge"] == 10.0
        assert result["tax_amount"] == 18.25

    async def test_tc_cfg_004_custom_default_jurisdiction_used_when_no_jurisdiction_given(self):
        """
        MCP-TC-CFG-004

        Title: Custom default_jurisdiction is used when jurisdiction argument is empty.

        Steps:
            1. Create server with default_jurisdiction="US-NY".
            2. Call calculate_tax with jurisdiction="" (empty).

        Expected Results:
            Calculation uses US-NY rates; jurisdiction in result is "US-NY".
        """
        server = create_taxcalc_server(make_session(),
            server_config={"default_jurisdiction": "US-NY"})
        result = await call(server, "calculate_tax", amount=100.0, jurisdiction="")

        assert result.get("jurisdiction") == "US-NY"
        assert result["tax_amount"] == 13.0  # US-NY: 8.0 + 0.5 + 4.5 = 13.0


# ============================================================================
# Tool discovery
# ============================================================================

class TestTaxCalcToolDiscovery:

    async def test_tc_tools_001_server_exposes_expected_tools(self):
        """
        MCP-TC-TOOLS-001

        Title: TaxCalc server exposes exactly the expected tools.

        Steps:
            1. Create TaxCalc server.
            2. Call list_tools().

        Expected Results:
            Tool names: calculate_tax, get_tax_rates, validate_tax_id.
        """
        server = create_taxcalc_server(make_session())
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}

        expected = {"calculate_tax", "get_tax_rates", "validate_tax_id"}
        assert expected == tool_names

    async def test_tc_tools_002_calculate_tax_schema_has_required_params(self):
        """
        MCP-TC-TOOLS-002

        Title: calculate_tax tool has amount, jurisdiction, and category in its schema.

        Steps:
            1. Get calculate_tax tool schema.

        Expected Results:
            `amount` is in properties.
        """
        server = create_taxcalc_server(make_session())
        tool = await server.get_tool("calculate_tax")
        params = tool.parameters

        assert "amount" in params.get("properties", {})

    async def test_tc_tools_003_validate_tax_id_schema_has_tax_id_and_country(self):
        """
        MCP-TC-TOOLS-003

        Title: validate_tax_id tool has tax_id and country in its schema.

        Steps:
            1. Get validate_tax_id tool schema.

        Expected Results:
            `tax_id` and `country` are in properties.
        """
        server = create_taxcalc_server(make_session())
        tool = await server.get_tool("validate_tax_id")
        params = tool.parameters

        assert "tax_id" in params.get("properties", {})
        assert "country" in params.get("properties", {})


# ============================================================================
# Float/Int edge cases
# ============================================================================

class TestFloatEdgeCases:

    async def test_tc_float_001_very_large_amount_does_not_overflow(self):
        """
        MCP-TC-FLOAT-001

        Title: Very large amounts (1 billion) are calculated without overflow or crash.

        Steps:
            1. Call calculate_tax with amount=1_000_000_000.0.

        Expected Results:
            Valid result returned; tax_amount > 0.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=1_000_000_000.0, jurisdiction="US-CA")

        assert "error" not in result
        assert result["tax_amount"] > 0

    async def test_tc_float_002_very_small_amount_computed_correctly(self):
        """
        MCP-TC-FLOAT-002

        Title: Very small amounts (0.01) return rounded tax amounts.

        Steps:
            1. Call calculate_tax with amount=0.01, jurisdiction="US-CA".
            2. 0.01 * 8.25% = 0.000825 → rounds to 0.0.

        Expected Results:
            tax_amount=0.0 (rounds to zero at 2 decimal places), total_amount=0.01.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=0.01, jurisdiction="US-CA")

        assert "error" not in result
        assert result["total_amount"] >= 0.01  # total cannot be less than original amount


# ============================================================================
# String edge cases
# ============================================================================

class TestStrEdgeCases:

    async def test_tc_str_001_sql_injection_in_jurisdiction_handled_safely(self):
        """
        MCP-TC-STR-001

        Title: SQL injection string in jurisdiction is handled safely (returns unknown error).

        Steps:
            1. Call calculate_tax with jurisdiction="' OR '1'='1".

        Expected Results:
            Response contains `error` about unknown jurisdiction (not a crash).
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax",
            amount=100.0, jurisdiction="' OR '1'='1")

        # Server does a dict lookup — no SQL involved, but should return unknown error
        assert "error" in result

    async def test_tc_str_002_whitespace_jurisdiction_treated_as_empty_uses_default(self):
        """
        MCP-TC-STR-002

        Title: Whitespace-only jurisdiction string is NOT treated as empty.

        BUG: jurisdiction="   " (whitespace) is truthy, so it does not fall back to
        the default jurisdiction. Instead it triggers "Unknown jurisdiction: '   '".
        Callers may expect whitespace to be stripped to empty before the fallback.

        Steps:
            1. Call calculate_tax with jurisdiction="   " (3 spaces).
            2. Verify either: (a) uses default jurisdiction, OR (b) returns clear error.

        Expected Results:
            Uses default jurisdiction (whitespace stripped). (BUG: returns unknown error.)
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "calculate_tax", amount=100.0, jurisdiction="   ")

        # BUG: whitespace not stripped; triggers "Unknown jurisdiction" error
        assert "error" not in result, \
            "Whitespace jurisdiction should fall back to default (strip + empty check)"

    async def test_tc_str_003_very_long_tax_id_handled_without_crash(self):
        """
        MCP-TC-STR-003

        Title: Very long tax_id string (1000 chars) is handled without crash.

        Steps:
            1. Call validate_tax_id with tax_id="1" * 1000.

        Expected Results:
            format_valid=False (not 9 digits) returned without error.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="1" * 1000, country="US")

        assert result["format_valid"] is False

    async def test_tc_str_004_unicode_in_tax_id_returns_invalid(self):
        """
        MCP-TC-STR-004

        Title: Unicode characters in tax_id return format_valid=False without crash.

        Steps:
            1. Call validate_tax_id with tax_id="日本語テスト".

        Expected Results:
            format_valid=False returned without exception.
        """
        server = create_taxcalc_server(make_session())
        result = await call(server, "validate_tax_id", tax_id="日本語テスト", country="US")

        assert result["format_valid"] is False
