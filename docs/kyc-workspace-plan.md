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
  - *FCA register*: firm reference number (FRN), from the free FCA register API (email and key in .env). Used for Section 2 and the industry.
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
7. **FCA register:** the user enters the firm reference number (FRN); the firm's details, every page of permissions, requirements, disciplinary history and linked individuals become an "FCA register record" source for Claude (industry and checks). The page shows the firm's name and status straight away and warns if the FCA's Companies House number differs from the company entered. **Done**

## Notes from building

- The answer format for the mapping call avoids "can be empty" fields: the API allows at most 16 of them.
- Prompt caching does not carry over from identifying to mapping (different effort settings), so it is not used yet.
- Legal form was removed from check 1.1 (26 Oct 2026, at the user's request) in all six checklists, the extraction and the rules; this also settles the earlier problem of it being copied as a sentence fragment.

## Industry-specific checklists (next)

Goal: pick the checklist that fits the company's industry (payments, crypto, investment management, ...).

1. **Show the industry codes (SIC codes) from Companies House** under the link box, with their official meanings (`data/sic_codes.csv`, from Companies House's public list). Free. **Done**
2. **Claude suggests the industry** from the questionnaire, the Companies House record (with SIC codes) and the website (FCA permissions once step 7 is done), with reasons and quotes; the user confirms or changes it. A mismatch between sources is flagged. Only those sources are sent, so it costs about 2p (measured $0.027 on the sample). **Done**
3. **The confirmed industry picks the checklist**, and the user can choose a different one from a dropdown. The checks run against the chosen checklist; saved answers are tied to the checklist's questions, so one checklist's answer is never replayed for another. **Done**
4. **The analyst can change a result** after the checks run, with a required reason and reviewer name; the original answer is kept beside it and changes can be undone. Saved per case (documents + checklist) in the git-ignored `reviews/` folder, so they are still there next time. **Done**

### Checklists per industry

Drafted by Claude (21 Oct 2026) and approved as written by a compliance professional (26 Oct 2026); built by
`scripts/make_industry_checklists.py` from the fintech checklist: general business, crypto, lending, investment firm and
asset management. Credit rating agencies were dropped (too niche). All keep the fintech sections so the app and the
Summary tab read them unchanged. Edit the script, not the spreadsheets; any content change needs a fresh review.

To connect: industry options become payments and e-money (fintech checklist), crypto, lending, investment firm,
asset management, not a financial business (general), and banking / insurance / other financial (fintech for now,
flagged as having no specific checklist). Rule for Claude: if it manages funds it is an asset manager, otherwise an
investment firm.
- FCA register API: requests need a named User-Agent (its security service blocks Python's default with "error code: 1010"). "Firm not found" comes back as a normal reply with no data. Public register links use an internal ID, not the FRN, so the page asks for the FRN.
- The sample pack fills in its questionnaire's specimen FRN 999999, which is not on the register, so the demo shows Claude catching a claimed licence the register does not support (2.1 Unclear, 2.2-2.4 Missing). Its saved answers were re-made with the FCA record for $0.24 and replay free.

## Version 1 roadmap

1. **Finalise the document reviewer** (in progress): landing page, entity details, name check, checklists, review page polish.
   - Done so far: landing page; two screens (Legal Entity Information, then the checks); saved drafts in the git-ignored `cases/` folder, with documents stored by fingerprint and Claude's answers kept per draft, so reopening costs nothing; documents can be added to or removed from a draft; five screens (details, documents, industry and checklist, checks, results) with Back and Next, keeping choices either way; drafts also keep label corrections and the industry and checklist choice (dropped if the documents change). Not yet: deleting drafts.
2. **Risk rating (last part of version 1):** suggest a rating for checklist 7.1 (customer, product, geography, delivery channel) from the evidence Clario already collects, flag enhanced due diligence triggers (7.2), and let the analyst confirm or change it with a reason; record senior approval for high-risk cases (7.3). Needs a scoring method (the firm's own, or a draft for compliance review). When it ships, update the landing page, which currently says Clario does not rate risk.
