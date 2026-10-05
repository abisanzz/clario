"""Create fake sample documents for testing the extractor.

Every document is for a fictitious company and is marked as a specimen.
Run from the project folder:  .venv/bin/python scripts/make_sample_documents.py
"""

from pathlib import Path

from fpdf import FPDF

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "sample_documents"
SPECIMEN = "SPECIMEN - FICTITIOUS COMPANY - NOT A REAL DOCUMENT"


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
    pdf.cell(0, 10, "Company Number 12345678", align="C", new_x="LMARGIN", new_y="NEXT")
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


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    target = OUTPUT_DIR / "certificate_of_incorporation.pdf"
    certificate_of_incorporation(target)
    print(f"Created {target.relative_to(OUTPUT_DIR.parent)}")
