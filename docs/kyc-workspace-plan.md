# KYC workspace plan

Goal: the first page is a workspace where the user uploads **every document they have for a company**, adds **links**, and sees **which of the 32 checklist items are present and which are missing**, with evidence.

## Decisions

- **Documents are identified by Claude.** The user drops in files with any names. Claude labels each one (certificate of incorporation, proof of address, articles, shareholder register, ...). The user can correct a label before the checks run.
- **All 32 checks are covered.** Claude maps the evidence for each check in one pass: status, a short finding, and quotes with document name and page.
  - Checks with evidence type *Screening tool* (6.1–6.3) and *Internal decision* (3.3, 7.1–7.4, 8.1–8.3) are not decided from documents. They show as "Not started" with "needs screening tool" or "analyst decision". Claude may still point to related evidence.
  - Our rule-based Section 1 checks (1.1–1.4) and live Companies House lookups run on top and take priority over Claude's view for those checks. Both are shown.
- **Links:**
  - *Companies House* (link or company number): company profile, officers and persons with significant control (PSC), from the free API. Used for 1.1, 1.3, 3.4, 4.1.
  - *Company website*: page text fetched on this computer, used as supporting evidence for Section 5.
  - *FCA register*: needs a free FCA API key (to be set up later). Used for Section 2.
- **Statuses** are the checklist's own: Present, Missing, Unclear, Needs human review, Not started.
- **Results page:** summary counts (like the spreadsheet's Summary tab), every check grouped by section with evidence, and two lists built from Missing or Unclear checks: **"Request from client"** (client documents and questionnaire) and **"Check on public registers"** (Companies House, FCA), each with its evidence source (column D).
- **Cost:** measured per company and shown on the page. Saved answers make sample demos free.
- **Privacy:** only fictitious or approved documents; uploads are sent to Anthropic.

## Order of work

1. **Fake document pack** for EXAMPLE PAYMENTS LTD (certificate, proof of address, articles, shareholder register, ID verification report, onboarding/AML questionnaire, board resolution), with deliberate gaps (e.g. no ownership chart) and one inconsistency, so the demo shows Present, Missing and Unclear. **Done**
2. **Links:** Companies House officers and PSC lookups; website text fetcher. Each becomes a text "document" that Claude can read. **Done**
3. **Document identifier** (Claude), with tests using a fake Claude. **Done**
4. **Evidence mapper** for all 32 checks (Claude) plus merging with the Section 1 rules, with tests. **Done**
5. **New workspace page:** upload, links, identify and confirm, run, results and request list. **Done**
6. **Real run** on the fake pack; measure cost; save answers for free demos. **Done** (about $0.09 to identify + $0.20 to map; saved answers replay free)
7. **FCA register** link, once an FCA API key is set up.

## Notes from building

- The answer format for the mapping call avoids "can be empty" fields: the API allows at most 16 of them.
- Prompt caching does not carry over from identifying to mapping (different effort settings), so it is not used yet.
- To tidy: the certificate's legal form was copied as a sentence fragment; tighten the instruction at the next paid re-run.

## Industry-specific checklists (next)

Goal: pick the checklist that fits the company's industry (payments, crypto, investment management, ...).

1. **Show the industry codes (SIC codes) from Companies House** under the link box, with their official meanings (`data/sic_codes.csv`, from Companies House's public list). Free. **Done**
2. **Claude suggests the industry** from the SIC codes, FCA permissions, questionnaire and website, with reasons; the user confirms or changes it. A mismatch between sources is flagged.
3. **The confirmed industry picks the checklist.** Needs one checklist spreadsheet per industry (to be written or drafted and reviewed).
