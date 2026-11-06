from services.pack import DocumentDetails
from services.verification import NOT_VERIFIED, RegisterRecord, check_facts, companies_house_record

STERLING = "Sterling Asset Management Limited"
DETAILS = {
    "04_Shareholder_Register.pdf": DocumentDetails(STERLING, "CLARIO-TEST-001", "20 Example Square, London, EC2A 4TEST",
                                                   owners=[("Amelia Hart", "60%"), ("Daniel Okafor", "40%")]),
    "06_PSC_Declaration.pdf": DocumentDetails(STERLING, "", "", people=[("Amelia Hart", "Director")],
                                              owners=[("Amelia Hart", "60%"), ("Daniel Okafor", "40%")]),
    "09_Director_and_Signatory_Register.pdf": DocumentDetails(STERLING, people=[("Amelia Hart", "Director"),
                                                                                ("Daniel Okafor", "Director")]),
}


def by_fact(checks):
    return {c.fact: c for c in checks}


def test_internally_consistent_facts_are_never_called_verified():
    checks = by_fact(check_facts(DETAILS))
    ownership = checks["Ownership"]
    assert ownership.extracted == "Amelia Hart 60%; Daniel Okafor 40%"
    assert ownership.cross_check == "Consistent across 2 documents" and ownership.consistent
    assert (ownership.external, ownership.externally_verified) == (NOT_VERIFIED, False)
    assert ownership.assessment == "Internally consistent, but external verification remains outstanding."
    assert checks["Company name"].cross_check == "Consistent across 3 documents"
    assert not any(c.externally_verified for c in checks.values())
    assert checks["FCA regulatory status"].external == NOT_VERIFIED  # a customer-supplied extract is not a check


def test_a_live_register_match_is_external_verification():
    register = RegisterRecord(STERLING.upper(), "CLARIO-TEST-001", "20 Example Square, London, EC2A 4TEST",
                              "EC2A 4TEST", ["HART, Amelia", "OKAFOR, Daniel"], ["Mrs Amelia Hart", "Mr Daniel Okafor"])
    checks = by_fact(check_facts(DETAILS, register, fca_status="Authorised"))
    for fact in ("Company name", "Registration number", "Registered address", "Directors", "Ownership",
                 "FCA regulatory status"):
        assert checks[fact].externally_verified, fact
    assert checks["Company name"].external == "Verified against Companies House"
    assert checks["Company name"].assessment == "Confirmed by a live Companies House check."


def test_a_register_mismatch_is_flagged_not_verified():
    register = RegisterRecord("STERLING HOLDINGS LIMITED", "12345678", "1 Other Street, Leeds, LS1 1AA", "LS1 1AA",
                              ["HART, Amelia"], ["Mrs Amelia Hart"])
    checks = by_fact(check_facts(DETAILS, register))
    assert checks["Company name"].external == "Does not match Companies House (STERLING HOLDINGS LIMITED)"
    assert not checks["Company name"].externally_verified
    assert checks["Directors"].external == "Not on Companies House as directors: Daniel Okafor"
    assert checks["Ownership"].external == "Not on the Companies House PSC register: Daniel Okafor"


def test_a_failed_or_missing_lookup_verifies_nothing():
    def not_found(number):
        raise LookupError("not on the register")
    assert companies_house_record(None, not_found, not_found, not_found) is None
    assert companies_house_record("CLARIO-TEST-001", not_found, not_found, not_found) is None

