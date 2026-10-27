"""Draft the KYC risk methodology that Clario's risk rating reads: factors, EDD triggers and how they combine.

DRAFT FOR REVIEW: written from general knowledge of the UK Money Laundering Regulations 2017 and common practice,
not checked against current legislation, JMLSG guidance or any firm's policy. A compliance professional must
approve it before it is relied on.
Run from the project folder (overwrites the draft):  .venv/bin/python scripts/make_risk_methodology.py
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

PATH = Path(__file__).resolve().parent.parent / "docs" / "UK_KYC_Risk_Methodology.xlsx"
DRAFTED_ON = "27 Oct 2026"
UNCHECKED = "Draft by Claude, not checked against current text"
HEADER_FILL = PatternFill("solid", fgColor="FF1F3864")  # the checklists' header colour
HEADER_FONT = Font(b=True, color="FFFFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")

FACTORS = [
    ("C", "Customer",
     "Simple ownership (UK individuals, or a listed or FCA-regulated parent); every beneficial owner and director "
     "identified and verified; no PEPs; no adverse findings; trading for 2 years or more; documents and registers "
     "agree.",
     "One layer of corporate ownership, or a fund or nominee shareholder with transparent owners; incorporated less "
     "than 2 years ago; gaps or inconsistencies that the client can resolve with more evidence.",
     "Complex or opaque structure (several layers, trusts, nominees, bearer shares); beneficial owners not "
     "identified; a PEP among owners, directors or signatories; adverse findings; unexplained inconsistencies between "
     "documents and registers; a claimed licence or registration not on the register.",
     "Ownership and people checks (sections 3 and 4), Companies House officers and PSC register, consistency findings, "
     "FCA register"),
    ("P", "Product and service",
     "A non-financial business with low-risk activity; or an FCA-regulated firm whose permissions match its activity, "
     "with no restrictions or enforcement.",
     "An FCA-regulated payments, e-money, lending, investment or asset management firm; holds or controls client "
     "money; some cash in the business; products that allow third-party payments.",
     "Cryptoasset activity; money remittance or currency exchange; activity that appears to need FCA authorisation "
     "but has none; cash-intensive or high-risk sectors (gambling, precious metals, arms, adult content); FCA "
     "restrictions or recent enforcement; anonymous or privacy-enhancing products.",
     "Industry and checklist chosen, FCA permissions and disciplinary history, business model and purpose "
     "(section 5), SIC codes"),
    ("G", "Geography",
     "Incorporated, operating and owned in the UK or other jurisdictions with equivalent anti-money-laundering "
     "regimes.",
     "Owners, customers, suppliers or operations in jurisdictions under increased FATF monitoring or with weaker "
     "anti-money-laundering regimes; offshore holding entities (for example Jersey, Guernsey, BVI) whose owners are "
     "transparent.",
     "Links to high-risk third countries (FATF call for action), sanctioned countries, or secrecy jurisdictions where "
     "ownership is not transparent.",
     "Registered office, countries served (5.1), owners' and holding entities' jurisdictions (3.5), suppliers and "
     "customers"),
    ("D", "Delivery channel",
     "A direct relationship; identity verified from reliable, independent sources (documents and electronic checks).",
     "Onboarded remotely without additional verification; introduced by a regulated third party or intermediary.",
     "Introduced by an unregulated intermediary; someone acts for the client without clear authority; the client is "
     "reluctant to provide information or to meet.",
     "Board resolution or signatory list (4.4), identity verification report (4.2), questionnaire"),
]

TRIGGERS = [
    ("T1", "A politically exposed person (PEP), or a family member or known close associate, among the beneficial "
           "owners, directors or signatories", "Money Laundering Regulations 2017, regulation 35", "Regulation"),
    ("T2", "Established in, or linked by ownership or business to, a high-risk third country (FATF call for action)",
     "Money Laundering Regulations 2017, regulation 33(1)(b), as amended in 2026", "Regulation"),
    ("T3", "Complex or unusually large transactions, or unusual patterns, with no apparent economic or legal purpose",
     "Money Laundering Regulations 2017, regulation 33(1)(f)", "Regulation"),
    ("T4", "Beneficial owners cannot be identified, or ownership runs through nominees, bearer shares or opaque trusts",
     "Money Laundering Regulations 2017, regulations 28 and 33(6)", "Regulation"),
    ("T5", "Cryptoasset activity", "Firm policy (cryptoasset correspondent relationship rules from 1 February 2027)",
     "Firm policy"),
    ("T6", "Claimed regulatory status not supported by the register, or FCA restrictions or enforcement",
     "Firm policy", "Firm policy"),
    ("T7", "Adverse media or a possible sanctions match from screening", "Firm policy; sanctions law", "Firm policy"),
]

RULES = [
    ("Overall rating", "The highest of the four factor ratings."),
    ("EDD triggers", "Any EDD trigger makes the overall rating High and requires enhanced due diligence."),
    ("Not enough information", "A factor without enough evidence counts as Medium and is flagged for the analyst."),
    ("Analyst confirmation", "The analyst confirms or changes the suggested rating; a change needs a reason."),
    ("High risk", "Needs senior management approval before onboarding (checklist 7.3)."),
    ("Review frequency", "Low: every 3 years. Medium: every 2 years. High: every year (checklist 8.1). Firm policy, "
                         "to confirm."),
]


def header(sheet, titles: list[str], widths: list[int]) -> None:
    sheet.append(titles)
    for column, width in enumerate(widths, start=1):
        cell = sheet.cell(1, column)
        cell.fill, cell.font, cell.alignment = HEADER_FILL, HEADER_FONT, WRAP
        sheet.column_dimensions[cell.column_letter].width = width
    sheet.freeze_panes = "A2"


def rows(sheet, values: list[tuple]) -> None:
    for row in values:
        sheet.append(list(row))
    for line in sheet.iter_rows(min_row=2):
        for cell in line:
            cell.alignment = WRAP


def build() -> Path:
    workbook = Workbook()
    factors = workbook.active
    factors.title = "Factors"
    header(factors, ["ID", "Factor", "Low", "Medium", "High", "Evidence Clario uses"], [6, 18, 45, 45, 50, 40])
    rows(factors, FACTORS)

    triggers = workbook.create_sheet("EDD triggers")
    header(triggers, ["ID", "Trigger (makes the rating High)", "Source", "Type", "Confidence"], [6, 70, 45, 14, 30])
    rows(triggers, [(*trigger, UNCHECKED) for trigger in TRIGGERS])

    rules = workbook.create_sheet("How it's decided")
    header(rules, ["Rule", "What happens"], [24, 100])
    rows(rules, RULES)

    guide = workbook.create_sheet("Guide")
    guide.column_dimensions["A"].width = 110
    for line in [
        "How to use this methodology",
        f"DRAFT FOR REVIEW: drafted by Claude on {DRAFTED_ON} from general knowledge of the UK Money Laundering "
        "Regulations 2017 and common practice. Have a compliance professional approve every row before relying on it.",
        "",
        "Scale: Low, Medium, High. High means enhanced due diligence and senior management approval.",
        "Clario suggests a rating for each factor with its reasons and evidence; fixed rules combine them as described "
        "on the 'How it's decided' tab; the analyst confirms or changes the result.",
        "Clario suggests, and does not make, the risk decision. Not legal advice.",
        "Edit scripts/make_risk_methodology.py and rebuild, rather than editing this file.",
    ]:
        guide.append([line])
    guide["A1"].font = Font(b=True, sz=14)
    guide["A2"].font = Font(b=True, color="FFC00000")
    for line in guide.iter_rows(min_row=2):
        line[0].alignment = WRAP

    workbook.save(PATH)
    return PATH


if __name__ == "__main__":
    print("Built", build().name)
