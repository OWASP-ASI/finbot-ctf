"""Detector Implementations"""

# Imports trigger registration via decorators
from finbot.ctf.detectors.implementations.cross_vendor_deletion import (
    CrossVendorDeletionDetector,
)
from finbot.ctf.detectors.implementations.gradual_status_flip import (
    GradualStatusFlipDetector,
)
from finbot.ctf.detectors.implementations.guardrail_prevention import (
    GuardrailPreventionDetector,
)
from finbot.ctf.detectors.implementations.indirect_exfil import (
    IndirectExfilDetector,
)
from finbot.ctf.detectors.implementations.inflated_payment import (
    InflatedPaymentDetector,
)
from finbot.ctf.detectors.implementations.invoice_threshold_bypass import (
    InvoiceThresholdBypassDetector,
)
from finbot.ctf.detectors.implementations.invoice_trust_override import (
    InvoiceTrustOverrideDetector,
)
from finbot.ctf.detectors.implementations.policy_bypass_non_compliant import (
    PolicyBypassNonCompliantDetector,
)
from finbot.ctf.detectors.implementations.rce import (
    RCEDetector,
)
from finbot.ctf.detectors.implementations.system_prompt_leak import (
    SystemPromptLeakDetector,
)
from finbot.ctf.detectors.implementations.tool_poisoning_deletion import (
    ToolPoisoningDeletionDetector,
)
from finbot.ctf.detectors.implementations.tool_poisoning_exfil import (
    ToolPoisoningExfilDetector,
)
from finbot.ctf.detectors.implementations.vendor_risk_downplay import (
    VendorRiskDownplayDetector,
)
from finbot.ctf.detectors.implementations.vendor_status_flip import (
    VendorStatusFlipDetector,
)

__all__ = [
    "CrossVendorDeletionDetector",
    "GradualStatusFlipDetector",
    "GuardrailPreventionDetector",
    "IndirectExfilDetector",
    "InflatedPaymentDetector",
    "InvoiceThresholdBypassDetector",
    "InvoiceTrustOverrideDetector",
    "PolicyBypassNonCompliantDetector",
    "RCEDetector",
    "SystemPromptLeakDetector",
    "ToolPoisoningDeletionDetector",
    "ToolPoisoningExfilDetector",
    "VendorRiskDownplayDetector",
    "VendorStatusFlipDetector",
]
