# Validator plan

Reference: `docs/UK_Fintech_KYC_Checklist.xlsx` (32 checks in 8 sections).
First version covers Section 1 (Legal existence) only.

## Decisions made

- **Reading the checklist:** use the `openpyxl` library to read the spreadsheet directly, so it stays the single source of truth.
- **Validator uses plain rules, not AI.** The extractor (`services/extractor.py`) pulls facts out of documents; the validator (`services/validator.py`) applies fixed rules to those facts. Same input, same answer, every time.
- **Read only.** The validator reads columns A–E of the checklist and does not write results back into the spreadsheet. Results are shown in the app.
- **Result for each check:** ID, Status, Finding (plain-English reason), Source reference (document, page). Reviewer and date are left for a person. Checks without rules yet show "Not started".
- **Red flags go to "Needs human review".** The checklist statuses describe the evidence, not pass/fail, so problems such as a dissolved company are escalated to a person rather than marked Present.
- **Check 1.3 uses the Companies House API.** The API key goes in `.env` (never committed). Tests use saved example responses and do not call the real API.

## Section 1 rules

**1.1 Registered name, company number, incorporation date, legal form** (certificate of incorporation)
- Present: all four found and valid.
- Missing: any of the four not found.
- Unclear: company number in the wrong format (8 characters, e.g. `12345678` or `SC123456`), incorporation date in the future, or name differs between documents.

**1.2 Registered office and principal place of business, if different** (proof of address)
- Present: registered office found; principal place of business also found if it is different.
- Missing: no registered office address.
- Unclear: documents suggest a different place of business but give no address for it.

**1.3 Company is active, accounts and confirmation statement up to date** (Companies House API)
- Present: active and nothing overdue.
- Missing: no company number to look up.
- Unclear: company number not found at Companies House.
- Needs human review: not active, filings overdue, or the lookup failed.

**1.4 Constitution and who can bind the company** (articles of association)
- Missing: no articles provided.
- Needs human review: articles provided (interpreting authority is a judgement call).

## Order of work

1. Load the 32 checks from the spreadsheet. **(Next step)**
2. Define the shape of a result.
3. Build check 1.1, with tests.
4. Build 1.2, then 1.4.
5. Build 1.3 with the Companies House connection.

## Open items

- Get a Companies House API key (REST, live environment) before step 5.
- Install `pytest` for running tests (ask first).
- Confirm the 1.3 rules, especially sending red flags to "Needs human review".
- Later: cross-check 1.1 and 1.2 against the Companies House record.
- Later: merge branch `add-kyc-checklist` into `main`.
