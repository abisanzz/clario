"""Customer details and the test-environment record kept with each assessment.

The environment (Live or Test) and data classification (Real or Synthetic) are metadata about the assessment, kept
separately from the customer's documents: they never become a document exception. A synthetic assessment's documents
are still assessed as if they were genuine evidence. External verification is never set here; it comes only from
checks against a trusted source (see services/verification.py).
"""

from dataclasses import dataclass

LIVE, TEST = "Live", "Test"
REAL, SYNTHETIC = "Real", "Synthetic"
ENVIRONMENTS = [LIVE, TEST]
CLASSIFICATIONS = [REAL, SYNTHETIC]
CUSTOMER_TYPES = ["Private limited company", "Public limited company", "Limited liability partnership",
                  "Partnership", "Sole trader", "Charity", "Trust", "Other"]

# What Clario AI is told when reading a synthetic assessment's documents
SYNTHETIC_NOTE = (
    "Test environment: the files below are synthetic test documents for a fictional customer. The application keeps "
    "their test status as separate metadata. Markings such as \"FICTIONAL TEST DOCUMENT\", \"CLARIO TEST DATA\", "
    "\"synthetic\" or \"not valid for due diligence\" are provenance labels: do not report them as missing, unclear, "
    "out-of-date or inconsistent evidence, and do not let them change a document's type. Read and assess the "
    "substantive content exactly as you would genuine customer-submitted evidence. A file that resembles a register "
    "extract (for example a Companies House profile or an FCA register entry) is still a customer-supplied document, "
    "not a live register result, so never treat it as independent verification."
)


@dataclass(frozen=True)
class TestMetadata:
    """The assessment's test-environment record."""

    customer_reference: str
    environment: str  # Live or Test
    data_classification: str  # Real or Synthetic

    @property
    def synthetic(self) -> bool:
        return self.data_classification == SYNTHETIC


def metadata_of(details: dict) -> TestMetadata:
    """The record for an assessment. The built-in example case is always test data."""
    if details.get("source") == "Sample pack":
        return TestMetadata(details.get("customer_reference", ""), TEST, SYNTHETIC)
    return TestMetadata(details.get("customer_reference", ""), details.get("environment") or LIVE,
                        details.get("data_classification") or REAL)
