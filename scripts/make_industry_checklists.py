"""Draft one KYC checklist per industry, as copies of the fintech checklist with industry-specific checks.

Each draft keeps the fintech workbook's layout, drop-downs, colours and Summary formulas. Sections 1, 3, 4, 6 and 8
apply to any company and are copied as they are; sections 2 and 5 and checks 7.2 and 8.2 change by
industry.

DRAFTS FOR REVIEW: written from general knowledge of UK rules, not checked against current legislation or FCA rules.
Run from the project folder (overwrites the drafts):  .venv/bin/python scripts/make_industry_checklists.py
"""

from copy import copy
from pathlib import Path

import openpyxl

DOCS = Path(__file__).resolve().parent.parent / "docs"
TEMPLATE = DOCS / "UK_Fintech_KYC_Checklist.xlsx"
DRAFTED_ON = "21 Oct 2026"
UNCHECKED = "Draft by Claude, not checked against current text"

CLIENT_DOC, QUESTIONNAIRE, REGISTER, SCREENING, INTERNAL = (
    "Client document", "Client questionnaire", "Public register", "Screening tool", "Internal decision")
FCA_REGISTER = "FCA Financial Services Register"
LEGAL, REGULATORY, OWNERSHIP, PEOPLE, BUSINESS, SCREEN, RISK, ONGOING = (
    "1. Legal existence", "2. Regulatory status", "3. Ownership and control", "4. People",
    "5. Business and relationship", "6. Screening", "7. Risk rating and escalation", "8. Ongoing")

RESTRICTIONS = ("Any FCA restrictions, warnings or enforcement history",
                "FCA Financial Services Register; FCA warning list", REGISTER)
AGENT_OR_AR = ("Directly authorised, or operating as an agent or appointed representative of another firm; "
               "if so, principal identified", FCA_REGISTER, REGISTER)
GENERIC_BUSINESS = [
    ("Business model, products, customer types and countries served", "AML / onboarding questionnaire", QUESTIONNAIRE),
    ("Purpose and intended nature of the relationship, with expected volumes and values",
     "AML / onboarding questionnaire", QUESTIONNAIRE),
    ("Source of funds (typically funding rounds, revenue or customer flows)",
     "AML / onboarding questionnaire; supporting evidence", QUESTIONNAIRE),
    ("Firm's own AML controls: named MLRO, policies, last audit or AML questionnaire",
     "AML / onboarding questionnaire", QUESTIONNAIRE),
]


def triggers(extra: str) -> tuple:
    return (f"Enhanced due diligence triggers checked: PEP involvement, complex or opaque structures, "
            f"high-risk jurisdictions, {extra}", "Risk assessment; screening results", INTERNAL)


def review_triggers(extra: str) -> tuple:
    return (f"Triggers for early review defined: change of ownership, change of permissions, new adverse media, {extra}",
            "Case file; monitoring set-up", INTERNAL)


INDUSTRIES = {
    "general": {
        "file": "UK_General_Business_KYC_Checklist.xlsx",
        "client": "a UK business that is not a financial services firm (for example a retailer, software company "
                  "or manufacturer)",
        "regulatory": [
            ("No FCA authorisation needed: the business model does not involve regulated activities, and the company "
             "is not on the FCA warning list", "AML / onboarding questionnaire; FCA Financial Services Register; "
             "FCA warning list", REGISTER),
            ("Registered for anti-money-laundering supervision if its sector needs it (estate agents, high value "
             "dealers, accountants, art market participants, trust or company service providers)",
             "HMRC register of supervised businesses; professional body register", REGISTER),
            ("Other licences its sector needs (for example gambling, alcohol, waste carrier, debt advice) identified "
             "and checked", "AML / onboarding questionnaire; relevant public register", QUESTIONNAIRE),
            ("VAT number, if registered, is valid and matches the company name", "HMRC VAT number check", REGISTER),
        ],
        "core_business": GENERIC_BUSINESS[:3],
        "business": [
            ("Evidence the business is real and trading: website, filed accounts, invoices, contracts or bank "
             "statements", "Company website; Companies House filed accounts; client documents", CLIENT_DOC),
            ("Expected account activity matches the size of the business (compared with turnover in the latest "
             "accounts); dormant or newly incorporated companies expecting large volumes flagged",
             "Annual accounts; Companies House filed accounts; AML / onboarding questionnaire", CLIENT_DOC),
            ("High-risk or cash-intensive sector identified (for example cash businesses, gambling, arms, precious "
             "metals, used cars, adult content)", "AML / onboarding questionnaire; Companies House SIC codes",
             QUESTIONNAIRE),
            ("Main suppliers and customers, and the countries they are in, including any sanctioned or high-risk "
             "jurisdictions", "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Trading address and staff consistent with the stated business; virtual or shared offices flagged",
             "AML / onboarding questionnaire; Company website", QUESTIONNAIRE),
        ],
        "edd": "cash-intensive or high-risk sectors, dormant or newly incorporated companies with large expected "
               "volumes, virtual offices",
        "review": "change of business activity, account activity well above what was expected",
        "figures": [
            ("EUR 10,000 in cash", "Businesses that accept cash payments of EUR 10,000 or more for goods (high value "
             "dealers) must register with HMRC for anti-money-laundering supervision.", "2.2",
             "Money Laundering Regulations 2017, regulations 14 and 56"),
            ("GBP 90,000", "VAT registration threshold from 1 April 2024: a business with taxable turnover above this "
             "should be VAT registered.", "2.4", "HMRC VAT Notice 700/1"),
            ("9 months", "A private company must file its accounts at Companies House within nine months of its year "
             "end; overdue or dormant accounts are a warning sign for an active trading account.", "1.3, 5.5",
             "Companies Act 2006, section 442"),
        ],
    },
    "crypto": {
        "file": "UK_Crypto_KYC_Checklist.xlsx",
        "client": "a UK cryptoasset business (exchange, broker, custodian or wallet provider)",
        "regulatory": [
            ("FCA registration as a cryptoasset exchange provider or custodian wallet provider under the Money "
             "Laundering Regulations, or authorisation under the FCA cryptoasset regime once it applies; "
             "firm reference number", "FCA Financial Services Register; FCA list of registered cryptoasset firms",
             REGISTER),
            ("Registration or permissions cover every activity being onboarded (exchange, custody, staking, "
             "lending, stablecoin issuance)", "FCA Financial Services Register", REGISTER),
            ("Licences or registrations in other countries where it serves customers (for example EU MiCA "
             "authorisation)", "AML / onboarding questionnaire; overseas regulator registers", QUESTIONNAIRE),
            RESTRICTIONS[:1] + ("FCA Financial Services Register; FCA warning list; FCA list of unregistered "
                                "cryptoasset businesses", REGISTER),
            ("How customer cryptoassets and money are held: segregation, custodians, hot and cold wallet split, "
             "proof of reserves", "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Financial promotions to UK consumers follow the cryptoasset promotion rules: communicated or approved "
             "by an authorised or registered firm, with the required risk warnings and cooling-off period",
             "Company website; AML / onboarding questionnaire", QUESTIONNAIRE),
        ],
        "business": [
            ("Travel rule: originator and beneficiary information collected and passed on for cryptoasset transfers, "
             "including how unhosted wallets are handled", "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Blockchain analytics tool used to screen wallet addresses and transaction exposure; provider named",
             "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Tokens offered and token listing policy; privacy coins and mixing services excluded or controlled",
             "AML / onboarding questionnaire; Company website", QUESTIONNAIRE),
            ("Banks and payment providers used to move money in and out of crypto (fiat on and off ramps) named",
             "AML / onboarding questionnaire", QUESTIONNAIRE),
        ],
        "edd": "crypto activity itself, privacy coins, unhosted wallets, cryptoasset correspondent relationships",
        "review": "change of registration status, hacks or loss of customer assets",
        "figures": [
            ("10 January 2020", "Cryptoasset exchange and custodian wallet providers had to register with the FCA "
             "for anti-money-laundering supervision from this date.", "2.1",
             "Money Laundering Regulations 2017, as amended by SI 2019/1511 (regulation 56)"),
            ("1 September 2023", "Travel rule in force: cryptoasset firms must collect and share information about "
             "the sender and recipient of transfers.", "5.5",
             "Money Laundering Regulations 2017, Part 7A (as amended by SI 2022/860)"),
            ("8 October 2023", "Cryptoasset financial promotions to UK consumers brought within the financial "
             "promotion rules (risk warnings, 24-hour cooling-off, appropriateness checks).", "2.6",
             "FCA Policy Statement PS23/6; COBS 4.12A"),
            ("FSMA cryptoasset regime", "Cryptoasset activities move from registration under the Money Laundering "
             "Regulations to full FCA authorisation. Start date to be confirmed (expected 2027).", "2.1, 2.2",
             "HM Treasury cryptoasset legislation and FCA consultation papers; confirm the current timetable"),
        ],
    },
    "lending": {
        "file": "UK_Lending_KYC_Checklist.xlsx",
        "client": "a UK lender (consumer or business lending, including buy now pay later and credit broking)",
        "regulatory": [
            ("FCA Financial Services Register entry: firm reference number and consumer credit permissions "
             "(lending, credit broking, debt collection); or, for business-only lending, why no FCA authorisation "
             "is needed", FCA_REGISTER, REGISTER),
            ("Permissions cover the products offered (for example high-cost short-term credit, deferred payment "
             "credit, hire purchase, regulated mortgages)", FCA_REGISTER, REGISTER),
            AGENT_OR_AR,
            ("Any FCA restrictions, warnings, enforcement history, redress schemes or past business reviews",
             "FCA Financial Services Register; FCA warning list; FCA notices", REGISTER),
            ("How affordability and creditworthiness are assessed, and how customers in financial difficulty or in "
             "vulnerable circumstances are treated (Consumer Duty)", "AML / onboarding questionnaire; credit policy",
             QUESTIONNAIRE),
        ],
        "business": [
            ("Source of lending capital: own funds, funding lines, warehouse facilities, securitisation or "
             "peer-to-peer investors, with funders named", "AML / onboarding questionnaire; funding agreements",
             QUESTIONNAIRE),
            ("Loan book: size, product mix, average loan size, arrears and default rates",
             "Latest management accounts or annual accounts", CLIENT_DOC),
            ("How borrowers repay and how money moves through the account (direct debit, continuous payment "
             "authority, card)", "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Collections and debt sale: done in-house or by named third parties",
             "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Fraud controls on borrowers: identity checks, application fraud and loan stacking",
             "AML / onboarding questionnaire", QUESTIONNAIRE),
        ],
        "edd": "high-cost lending, lending into high-risk jurisdictions, funders that cannot be identified",
        "review": "change of funders, a rise in complaints or FCA redress action",
        "figures": [
            ("31 July 2023", "Consumer Duty applies to open products (31 July 2024 for closed products): firms must "
             "deliver good outcomes for retail customers.", "2.5", "FCA Principle 12; PRIN 2A"),
            ("0.8% a day; 100% total cost", "Price cap on high-cost short-term credit: interest and fees of no more "
             "than 0.8% a day, and total cost no more than the amount borrowed.", "2.2", "FCA CONC 5A"),
            ("15 July 2026", "Deferred payment credit (buy now pay later) brought into FCA regulation; lenders need "
             "the relevant permission.", "2.1, 2.2",
             "Financial Services and Markets Act 2000 (Regulated Activities) (Amendment) Order 2025; confirm"),
        ],
    },
    "investment": {
        "file": "UK_Investment_Firm_KYC_Checklist.xlsx",
        "client": "a UK investment firm (broker, dealer, wealth manager or investment adviser)",
        "regulatory": [
            ("FCA Financial Services Register entry: firm reference number, authorised under Part 4A of FSMA, and "
             "prudential category (for example MIFIDPRU investment firm)", FCA_REGISTER, REGISTER),
            ("Permissions cover the activities being onboarded (dealing, arranging, advising, managing investments, "
             "safeguarding and administering assets) and the client types allowed (retail or professional)",
             FCA_REGISTER, REGISTER),
            AGENT_OR_AR,
            RESTRICTIONS,
            ("Whether it holds client money or custody assets, under the CASS rules: banks and custodians named, "
             "CASS oversight officer, latest client assets audit", "AML / onboarding questionnaire; CASS audit report",
             QUESTIONNAIRE),
            ("Senior managers approved on the register, including the money laundering reporting officer (SMF17) and "
             "compliance oversight (SMF16)", FCA_REGISTER, REGISTER),
        ],
        "business": [
            ("Its own clients: retail, professional or high-net-worth, where they are based, and how it does KYC on "
             "them", "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Products traded, including complex or high-risk products (derivatives, contracts for difference)",
             "AML / onboarding questionnaire; Company website", QUESTIONNAIRE),
            ("Execution venues, brokers, custodians and clearing arrangements named",
             "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Financial position: latest annual accounts and regulatory capital", "Annual accounts; capital return",
             CLIENT_DOC),
        ],
        "edd": "omnibus or nominee accounts holding other people's assets, high-risk products",
        "review": "change of senior managers, client assets (CASS) breaches",
        "figures": [
            ("1 January 2022", "Investment firms prudential regime (IFPR) in force: most UK investment firms are "
             "MIFIDPRU investment firms.", "2.1", "FCA MIFIDPRU sourcebook"),
            ("9 December 2019", "Senior Managers and Certification Regime extended to FCA solo-regulated firms; senior "
             "managers are shown on the register.", "2.6", "FCA SYSC 24-27; FCA Handbook SUP 10C"),
            ("Annual", "Firms holding client money or custody assets must send the FCA a client assets report from "
             "their auditor each year.", "2.5", "FCA CASS sourcebook; SUP 3.10"),
            ("31 July 2023", "Consumer Duty applies to retail business (31 July 2024 for closed products).", "5.5",
             "FCA Principle 12; PRIN 2A"),
        ],
    },
    "asset_management": {
        "file": "UK_Asset_Management_KYC_Checklist.xlsx",
        "client": "a UK asset manager (fund manager, AIFM or UCITS management company), or a fund it manages",
        "regulatory": [
            ("FCA Financial Services Register entry: firm reference number and type (full-scope UK AIFM, small AIFM, "
             "UCITS management company or portfolio manager)", FCA_REGISTER, REGISTER),
            ("Permissions cover the activities being onboarded (managing an AIF or UCITS, managing investments) and "
             "whether it may deal with retail investors", FCA_REGISTER, REGISTER),
            ("Directly authorised, or operating under a third-party host manager or as an appointed representative; "
             "if so, the host or principal identified", FCA_REGISTER, REGISTER),
            RESTRICTIONS,
            ("Funds managed: name, legal form, domicile and regulator; and whether the customer is the manager or a "
             "fund", "Prospectus or private placement memorandum; fund register entries", CLIENT_DOC),
            ("Fund service providers named: depositary, administrator, auditor and transfer agent",
             "Prospectus or private placement memorandum", CLIENT_DOC),
        ],
        "ownership": [
            ("For a fund customer: investors with more than 25% identified, or the manager or general partner recorded "
             "as the controller", "Fund investor register; fund constitution", CLIENT_DOC),
        ],
        "business": [
            ("Investor base, and who performs investor due diligence (manager, administrator or transfer agent)",
             "AML / onboarding questionnaire", QUESTIONNAIRE),
            ("Investment strategy, asset classes and countries invested in", "Prospectus; fund factsheet",
             CLIENT_DOC),
            ("Delegation: portfolio or risk management delegated to other firms, which are named",
             "AML / onboarding questionnaire; prospectus", QUESTIONNAIRE),
            ("Sustainability claims consistent with the FCA anti-greenwashing rule and any sustainability labels used",
             "Company website; fund documents", QUESTIONNAIRE),
        ],
        "edd": "investors from high-risk jurisdictions, nominee investors, private assets in high-risk sectors",
        "review": "new funds launched, change of depositary or administrator",
        "figures": [
            ("EUR 100m / EUR 500m", "Thresholds below which an alternative investment fund manager can be a small "
             "(sub-threshold) AIFM: EUR 100m of assets with leverage, or EUR 500m unleveraged with no redemption "
             "rights for five years. Reforms to the UK AIFM regime are under way.", "2.1",
             "Alternative Investment Fund Managers Regulations 2013; confirm current thresholds"),
            ("31 May 2024", "Anti-greenwashing rule in force: sustainability claims must be fair, clear and not "
             "misleading.", "5.8", "FCA ESG 4.1.1R; Policy Statement PS23/16"),
            ("31 July 2024", "Sustainability labels available to UK funds under the Sustainability Disclosure "
             "Requirements (SDR).", "5.8", "FCA Policy Statement PS23/16"),
        ],
    },
}


def checks_for(industry: dict, fintech: list[tuple]) -> list[tuple]:
    """(id, section, check, evidence source, evidence type) rows for one industry."""
    by_section = {}
    for row in fintech:
        by_section.setdefault(row[1], []).append(row)

    def numbered(section, number, rows):
        return [(f"{number}.{i}", section, *row) for i, row in enumerate(rows, start=1)]

    rows = [r for r in by_section[LEGAL]]
    rows += numbered(REGULATORY, 2, industry["regulatory"])
    rows += numbered(OWNERSHIP, 3, [r[2:] for r in by_section[OWNERSHIP]] + industry.get("ownership", []))
    rows += by_section[PEOPLE]
    rows += numbered(BUSINESS, 5, industry.get("core_business", GENERIC_BUSINESS) + industry["business"])
    rows += by_section[SCREEN]
    risk = by_section[RISK]
    rows += [r if r[0] != "7.2" else ("7.2", RISK, *triggers(industry["edd"])) for r in risk]
    rows += [r if r[0] != "8.2" else ("8.2", ONGOING, *review_triggers(industry["review"])) for r in by_section[ONGOING]]
    return rows


def copy_style(sheet, from_row: int, to_row: int, columns: int):
    for column in range(1, columns + 1):
        sheet.cell(to_row, column)._style = copy(sheet.cell(from_row, column)._style)
    sheet.row_dimensions[to_row].height = sheet.row_dimensions[from_row].height


def build(key: str, industry: dict) -> Path:
    workbook = openpyxl.load_workbook(TEMPLATE)
    sheet = workbook["Checklist"]
    fintech = [tuple(c.value for c in row[:5]) for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row)
               if row[0].value]
    rows = checks_for(industry, fintech)

    last_template_row = len(fintech) + 1
    for number in range(2, max(len(rows), len(fintech)) + 2):
        row = rows[number - 2] if number - 2 < len(rows) else None
        # Checklist rows look like the template's last row; rows past the end are plain
        copy_style(sheet, last_template_row if row else last_template_row + 1, number, 10)
        for column in range(1, 11):
            sheet.cell(number, column).value = None
        if row:
            for column, value in enumerate(row, start=1):
                sheet.cell(number, column).value = value
            sheet.cell(number, 6).value = "Not started"
    sheet.auto_filter.ref = f"A1:J{len(rows) + 1}"

    figures = workbook["Key figures"]
    start = figures.max_row + 1
    for offset, (figure, meaning, used_in, source) in enumerate(industry["figures"]):
        copy_style(figures, start - 1, start + offset, 5)
        for column, value in enumerate((figure, meaning, used_in, source, UNCHECKED), start=1):
            figures.cell(start + offset, column).value = value

    guide = workbook["Guide"]
    guide["A2"] = (f"DRAFT FOR REVIEW: drafted by Claude on {DRAFTED_ON} from general knowledge of UK rules. "
                   "Have a compliance professional check every row before relying on it.")
    guide["A2"].font = openpyxl.styles.Font(b=True, sz=11, color="FFC00000")
    guide["B25"] = f"The client is {industry['client']}, being onboarded as a corporate client by a regulated " \
                   "financial-services firm."
    extra = [
        "Sections 2 and 5, checks 7.2 and 8.2, and any check added at the end of section 3 are specific to this "
        "industry; everything else is the same as the fintech checklist.",
        "Key figures added for this industry are marked 'Draft by Claude, not checked against current text'.",
    ]
    for offset, text in enumerate(extra, start=31):
        copy_style(guide, 30, offset, 2)
        guide.cell(offset, 1).value, guide.cell(offset, 2).value = "-", text

    path = DOCS / industry["file"]
    workbook.save(path)
    return path


if __name__ == "__main__":
    for key, industry in INDUSTRIES.items():
        print("Drafted", build(key, industry).name)
