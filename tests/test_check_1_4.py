from dataclasses import replace

import pytest

from services.documents import ArticlesOfAssociation, CertificateOfIncorporation, Fact
from services.validator import Status, check_1_4

ARTICLES_P1 = "Articles of association p.1"
ARTICLES_P7 = "Articles of association p.7"
SUMMARY = "Directors manage the business; any two directors may sign on the company's behalf"

CERTIFICATE = CertificateOfIncorporation(company_name=Fact("EXAMPLE PAYMENTS LTD", "Certificate of incorporation p.1"))


def articles(**changes):
    """Complete made-up articles; pass changes to break one part of them."""
    good = ArticlesOfAssociation(
        company_name=Fact("Example Payments Limited", ARTICLES_P1),
        authority_summary=Fact(SUMMARY, ARTICLES_P7),
    )
    return replace(good, **changes)


def test_no_articles_is_missing():
    result = check_1_4(None, CERTIFICATE)
    assert result.check_id == "1.4"
    assert result.status is Status.MISSING
    assert result.finding == "No articles of association provided"


def test_articles_with_summary_go_to_human_review():
    result = check_1_4(articles(), CERTIFICATE)
    assert result.status is Status.NEEDS_HUMAN_REVIEW
    assert result.finding == (
        f"Articles provided. Authority ({ARTICLES_P7}): {SUMMARY}. Analyst to confirm who can bind the company"
    )
    assert result.source_reference == f"{ARTICLES_P1}; {ARTICLES_P7}"


@pytest.mark.parametrize("empty", [None, "", "  "])
def test_articles_without_summary_go_to_human_review(empty):
    result = check_1_4(articles(authority_summary=Fact(empty)), CERTIFICATE)
    assert result.status is Status.NEEDS_HUMAN_REVIEW
    assert result.finding == (
        "Articles provided but no description of signing authority was found; analyst to read the articles"
    )


def test_summary_without_page_still_shown():
    result = check_1_4(articles(authority_summary=Fact(SUMMARY)), CERTIFICATE)
    assert f"Authority: {SUMMARY}" in result.finding


def test_different_company_name_is_unclear_and_keeps_summary():
    result = check_1_4(articles(company_name=Fact("OTHER CO LTD", ARTICLES_P1)), CERTIFICATE)
    assert result.status is Status.UNCLEAR
    assert result.finding == (
        f"Articles are for 'OTHER CO LTD', certificate says 'EXAMPLE PAYMENTS LTD'. "
        f"Also: authority ({ARTICLES_P7}): {SUMMARY}"
    )


def test_no_company_name_on_articles_is_unclear():
    result = check_1_4(articles(company_name=Fact()), CERTIFICATE)
    assert result.status is Status.UNCLEAR
    assert result.finding.startswith("Company name not found on articles, so they cannot be matched to the client")


def test_name_not_compared_without_certificate():
    assert check_1_4(articles(), None).status is Status.NEEDS_HUMAN_REVIEW


@pytest.mark.parametrize("case", [
    articles(),
    articles(authority_summary=Fact()),
    articles(company_name=Fact()),
    articles(company_name=Fact("OTHER CO LTD")),
    None,
])
def test_never_present(case):
    assert check_1_4(case, CERTIFICATE).status is not Status.PRESENT
