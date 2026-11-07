from services.information import Row, from_documents_and_registers, provided_by_analyst
from services.pack import DocumentDetails

NAMES = {"cert.pdf", "articles.pdf", "register.pdf", "questionnaire.pdf"}
DETAILS = {
    "cert.pdf": DocumentDetails("EXAMPLE PAYMENTS LTD", "99999901"),
    "articles.pdf": DocumentDetails("Example Payments Limited", "99999901"),  # the same name, written differently
    "register.pdf": DocumentDetails("EXAMPLE PAYMENTS LTD", owners=[("Alex Sample", "60%"), ("Jamie Example", "25%")],
                                    people=[("Alex Sample", "Director")]),
    "questionnaire.pdf": DocumentDetails(owners=[("Alex Sample", "60%"), ("Jamie Example", "28%")],
                                         people=[("Alex Sample", "Chief Executive")]),
}
FACTS_1_1 = [("Company name", "EXAMPLE PAYMENTS LTD", "cert.pdf p.1"), ("Incorporated", "14 Mar 2019", "cert.pdf p.1")]


def rows_for(check_id="1.1", section="1. Legal existence", line_facts=FACTS_1_1, evidence=()):
    return from_documents_and_registers(check_id, section, line_facts, DETAILS, list(evidence), NAMES)


def test_a_value_found_in_several_documents_is_one_row_listing_them_all_with_pages_kept():
    rows, _ = rows_for()
    name = next(row for row in rows if row.label == "Company name")
    assert name.value == "EXAMPLE PAYMENTS LTD" and not name.disagree
    # three documents agree (capitals and Limited/Ltd ignored); the certificate's page comes from the rules' fact
    assert name.sources == ["cert.pdf, page 1", "articles.pdf", "register.pdf"]
    assert Row("Incorporated", "14 Mar 2019", ["cert.pdf, page 1"]) in rows
    assert next(row for row in rows if row.label == "Company number").sources == ["cert.pdf", "articles.pdf"]


def test_a_quote_repeating_a_listed_value_joins_its_row_and_other_quotes_get_their_own():
    rows, _ = rows_for(evidence=['cert.pdf p.1: "EXAMPLE PAYMENTS LTD"', 'cert.pdf p.1: "Company Number 99999901"',
                                'articles.pdf p.2: "Company Number 99999901"'])
    assert [row.label for row in rows].count("Company name") == 1  # the quote did not add a second name row
    quoted = [row for row in rows if row.label == "Quoted"]
    assert quoted == [Row("Quoted", "Company Number 99999901", ["cert.pdf, page 1", "articles.pdf, page 2"])]


def test_owners_show_where_the_documents_disagree():
    rows, _ = rows_for("3.2", "3. Ownership and control", line_facts=[])
    owners = {(row.label, row.value): row for row in rows}
    assert owners[("Owner Alex Sample", "60%")] == Row("Owner Alex Sample", "60%", ["register.pdf", "questionnaire.pdf"])
    assert owners[("Owner Jamie Example", "25%")].disagree and owners[("Owner Jamie Example", "28%")].disagree
    assert owners[("Owner Jamie Example", "28%")].sources == ["questionnaire.pdf"]


def test_people_lines_list_each_person_and_their_roles():
    rows, _ = rows_for("4.1", "4. People", line_facts=[])
    assert Row("Person Alex Sample", "Director, Chief Executive", ["register.pdf", "questionnaire.pdf"]) in rows


def test_register_and_website_results_are_kept_apart_from_the_documents():
    rows, registers = rows_for(evidence=[
        'Companies House record: "There is no company with number 99999901"',
        'Company website: "Example Payments, regulated by the FCA"',
        "Companies House API, checked 07 Nov 2026",  # a reference the rules added
        "cert.pdf p.1",  # the rules pointing back to a document already listed: left out
    ])
    assert registers == ["“There is no company with number 99999901” · Companies House record",
                         "“Example Payments, regulated by the FCA” · Company website",
                         "Companies House API, checked 07 Nov 2026"]
    assert not any(row.label == "Quoted" for row in rows)


def test_what_the_analyst_provided_follows_the_line():
    supporting = [{"name": "bill.pdf", "description": "Utility bill", "added_by": "A. Analyst",
                   "added_on": "2026-11-07", "verdict": "Present", "verdict_finding": "Dated last month"}]
    provided = provided_by_analyst("1.1", "Certificate of incorporation", "Example Payments Ltd", "99999901",
                                   "999999", "example.com", supporting)
    assert provided == [
        ("Legal entity name entered", "Example Payments Ltd", ""),
        ("Company number entered", "99999901", ""),
        ("Supporting document", "bill.pdf",
         "(Utility bill) added by A. Analyst on 2026-11-07. Clario AI: Present. Dated last month"),
    ]
    # the FCA reference and website only where the line's evidence comes from them
    assert provided_by_analyst("2.1", "FCA register; company website", "", "", "999999", "example.com", []) == [
        ("FCA firm reference number entered", "999999", ""), ("Website entered", "example.com", "")]
    assert provided_by_analyst("5.1", "Annual accounts", "Name", "99999901", "999999", "example.com", []) == []
