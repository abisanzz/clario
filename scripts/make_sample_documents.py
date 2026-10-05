"""Create fake sample documents for testing the extractor.

Every document is for a fictitious company and is marked as a specimen.
Run from the project folder:  .venv/bin/python scripts/make_sample_documents.py
"""

from pathlib import Path

from fpdf import FPDF

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "sample_documents"
SPECIMEN = "SPECIMEN - FICTITIOUS COMPANY - NOT A REAL DOCUMENT"
# Checked on 5 Oct 2026: this number is not on the Companies House register
NUMBER = "99999901"


class SpecimenPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(200, 0, 0)
        self.cell(0, 8, SPECIMEN, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(200, 0, 0)
        self.cell(0, 8, f"{SPECIMEN} - page {self.page_no()}", align="C")


def certificate_of_incorporation(path: Path) -> None:
    pdf = SpecimenPDF()
    pdf.add_page()
    pdf.ln(20)

    pdf.set_font("Times", "B", 20)
    pdf.cell(0, 12, "CERTIFICATE OF INCORPORATION", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 14)
    pdf.cell(0, 10, "OF A PRIVATE LIMITED COMPANY", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)

    pdf.set_font("Times", "", 13)
    pdf.cell(0, 10, f"Company Number {NUMBER}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    pdf.multi_cell(0, 8, "The Registrar of Companies for England and Wales, hereby certifies that", align="C")
    pdf.ln(6)
    pdf.set_font("Times", "B", 16)
    pdf.cell(0, 12, "EXAMPLE PAYMENTS LTD", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Times", "", 13)
    pdf.multi_cell(
        0, 8,
        "is this day incorporated under the Companies Act 2006 as a private company, "
        "that the company is limited by shares, and the situation of its registered "
        "office is in England and Wales",
        align="C",
    )
    pdf.ln(16)
    pdf.multi_cell(0, 8, "Given at Companies House, Cardiff, on 14th March 2019", align="C")

    pdf.output(str(path))


# --- Simple documents: a title, then headings, paragraphs and tables ---

COMPANY = "EXAMPLE PAYMENTS LTD"
OFFICE = "1 Example Street, London EX1 1AA"


def simple_document(path: Path, title: str, blocks: list) -> None:
    """blocks: ("h", heading), ("p", paragraph), ("table", [header row, row, ...]) or ("page", None)."""
    pdf = SpecimenPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    for kind, content in blocks:
        if kind == "page":
            pdf.add_page()
        elif kind == "h":
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, content, new_x="LMARGIN", new_y="NEXT")
        elif kind == "p":
            pdf.set_font("Helvetica", "", 10.5)
            pdf.multi_cell(0, 6, content, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif kind == "table":
            pdf.set_font("Helvetica", "", 9.5)
            with pdf.table(first_row_as_headings=True, line_height=6) as table:
                for row in content:
                    table.row(row)
            pdf.ln(2)
    pdf.output(str(path))


def proof_of_address(path: Path) -> None:
    simple_document(path, "Example Energy Supply (specimen) - Business electricity bill", [
        ("table", [["Bill date", "Account number", "Billing period"],
                   ["2 September 2026", "EE-000-1234", "1 Aug 2026 - 31 Aug 2026"]]),
        ("h", "Account holder and supply address"),
        ("p", f"{COMPANY}\n{OFFICE}"),
        ("h", "Summary"),
        ("table", [["Item", "Amount"], ["Electricity used (1,240 kWh)", "GBP 372.00"],
                   ["Standing charge (31 days)", "GBP 18.60"], ["VAT at 20%", "GBP 78.12"],
                   ["Total due", "GBP 468.72"]]),
    ])


def articles_of_association(path: Path) -> None:
    simple_document(path, f"Articles of Association of {COMPANY}", [
        ("p", f"Company number {NUMBER}. Private company limited by shares. Adopted by special resolution on 14 March 2019."),
        ("h", "1. Model articles"),
        ("p", "The model articles for private companies limited by shares in Schedule 1 to the Companies "
              "(Model Articles) Regulations 2008 apply to the company, except where they are modified below."),
        ("h", "2. Directors' general authority"),
        ("p", "Subject to these articles, the directors are responsible for the management of the company's "
              "business, for which purpose they may exercise all the powers of the company."),
        ("page", None),
        ("h", "3. Execution of documents"),
        ("p", "A document is validly executed by the company if it is signed by any two directors, or by one "
              "director in the presence of a witness who attests the signature."),
        ("h", "4. Quorum"),
        ("p", "The quorum for directors' meetings is two directors."),
        ("h", "5. Share capital"),
        ("p", "The company has one class of ordinary shares of GBP 0.01 each, each carrying one vote."),
    ])


def register_of_members(path: Path) -> None:
    simple_document(path, f"Register of Members - {COMPANY}", [
        ("p", f"Company number {NUMBER}. Ordinary shares of GBP 0.01. Position as at 1 September 2026."),
        ("table", [["Member", "Address", "Shares held", "% of shares and votes"],
                   ["Alex Sample", "10 Sample Lane, London EX2 2BB", "600,000", "60%"],
                   ["Jamie Example", "22 Example Road, Manchester EX3 3CC", "250,000", "25%"],
                   ["Example Ventures Fund I LP", "c/o Example Ventures Manager Ltd, Jersey", "150,000", "15%"],
                   ["Total", "", "1,000,000", "100%"]]),
    ])


def register_of_directors(path: Path) -> None:
    simple_document(path, f"Register of Directors - {COMPANY}", [
        ("p", f"Company number {NUMBER}. Position as at 1 September 2026."),
        ("table", [["Name", "Date of birth", "Service address", "Appointed", "Role"],
                   ["Alex Sample", "12 April 1985", OFFICE, "14 March 2019", "Chief Executive"],
                   ["Jamie Example", "3 November 1988", OFFICE, "14 March 2019", "Chief Technology Officer"],
                   ["Sam Placeholder", "21 July 1979", OFFICE, "1 June 2022", "Chief Risk Officer and MLRO"]]),
    ])


def id_verification_report(path: Path) -> None:
    simple_document(path, "Identity verification report (specimen provider: VerifyCo)", [
        ("p", f"Prepared for the onboarding of {COMPANY} on 3 September 2026."),
        ("table", [["Individual", "Date of birth", "Residential address", "Document checked", "Result"],
                   ["Alex Sample", "12 April 1985", "10 Sample Lane, London EX2 2BB", "UK passport", "Verified"],
                   ["Jamie Example", "3 November 1988", "22 Example Road, Manchester EX3 3CC", "UK driving licence", "Verified"]]),
        ("p", "No other individuals were submitted for verification."),
    ])


def onboarding_questionnaire(path: Path) -> None:
    simple_document(path, f"Onboarding and AML questionnaire - {COMPANY}", [
        ("p", "Completed by Sam Placeholder, Chief Risk Officer and MLRO, on 1 September 2026."),
        ("h", "A. Regulatory status"),
        ("p", "Q1. Is the firm regulated? Yes. Authorised Payment Institution, FCA firm reference number 999999 (specimen)."),
        ("p", "Q2. Does the firm hold customer funds? Yes. Customer funds are safeguarded in a segregated "
              "safeguarding account with Example Bank plc, reconciled daily."),
        ("h", "B. Ownership"),
        ("p", "Q3. Who owns more than 25% of the company? Alex Sample (60%) and Jamie Example (28%). "
              "Example Ventures Fund I LP holds the remaining shares."),
        ("h", "C. Business and relationship"),
        ("p", "Q4. Business model: a payments app that lets small UK and Irish businesses collect card and "
              "open-banking payments. Customers are small and medium-sized businesses in the UK and Ireland."),
        ("p", "Q5. Purpose of the account: operational account for fee income and supplier payments, plus a "
              "safeguarding account. Expected volume: about 400 payments a month, around GBP 1.2 million a month."),
        ("p", "Q6. Source of funds: a seed funding round of GBP 2 million led by Example Ventures Fund I LP "
              "in 2024, and transaction fee revenue."),
        ("p", "Q7. Does the firm trade from its registered office? Yes."),
        ("page", None),
        ("h", "D. Financial crime controls"),
        ("p", "Q8. MLRO: Sam Placeholder."),
        ("p", "Q9. Policies: AML and counter-terrorist financing policy, sanctions policy and customer due "
              "diligence procedure, all approved by the board in January 2026."),
        ("p", "Q10. Last independent AML audit: March 2026, by a specimen audit firm. No high-risk findings."),
    ])


def board_resolution(path: Path) -> None:
    simple_document(path, f"Written resolution of the directors of {COMPANY}", [
        ("p", f"Company number {NUMBER}. Dated 2 September 2026."),
        ("p", "IT IS RESOLVED that the company opens accounts with the onboarding bank, and that any two of "
              "Alex Sample and Jamie Example are authorised to give instructions and sign on those accounts."),
        ("table", [["Director", "Signature"], ["Alex Sample", "(signed)"], ["Jamie Example", "(signed)"],
                   ["Sam Placeholder", "(signed)"]]),
    ])


DOCUMENTS = {
    "certificate_of_incorporation.pdf": certificate_of_incorporation,
    "pack/electricity_bill_sept_2026.pdf": proof_of_address,
    "pack/articles_of_association.pdf": articles_of_association,
    "pack/register_of_members.pdf": register_of_members,
    "pack/register_of_directors.pdf": register_of_directors,
    "pack/id_verification_report.pdf": id_verification_report,
    "pack/onboarding_questionnaire.pdf": onboarding_questionnaire,
    "pack/board_resolution.pdf": board_resolution,
}


if __name__ == "__main__":
    # Only create missing files: rebuilding a PDF changes its fingerprint, which would
    # make saved Claude answers stop matching and cost a fresh read.
    for name, make in DOCUMENTS.items():
        target = OUTPUT_DIR / name
        if target.exists():
            print(f"Kept    {target.relative_to(OUTPUT_DIR.parent)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        make(target)
        print(f"Created {target.relative_to(OUTPUT_DIR.parent)}")
