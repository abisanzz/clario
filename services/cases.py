"""Draft reviews saved on this computer: the entity's details and its documents, so a review can be continued later.

Each draft has its own folder in the cases folder, holding case.json, the documents (stored under a fingerprint of
their contents, never under the uploaded file name) and Claude's saved answers. The folder is git-ignored: drafts
hold client documents and must not be committed.
"""

import json
import secrets
import shutil
from datetime import datetime
from pathlib import Path

from services.companies_house import parse_company_number
from services.pack import DocumentLabel, UploadedDocument
from services.validator import normalise_company_name

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"
DETAIL_FIELDS = ("source", "entity_name", "company_link", "website", "fca_frn", "country", "registration_number",
                 "stated_industry", "owner", "customer_reference",
                 "customer_type")  # owner: whoever created the assessment, until an analyst reassigns it
CUSTOMER_TYPES = ["Private limited company", "Public limited company", "Limited liability partnership",
                  "Partnership", "Sole trader", "Charity", "Trust", "Other"]


def new_case_id() -> str:
    """A short random name for a new draft's folder."""
    return datetime.now().strftime("%Y%m%d-") + secrets.token_hex(4)


def _folder(case_id: str, folder: Path | None) -> Path:
    if not case_id or any(c not in "0123456789abcdef-" for c in case_id):
        raise ValueError(f"'{case_id}' is not a draft name")
    return (folder or CASES_DIR) / case_id


def save_case(case_id: str, details: dict, documents: list[UploadedDocument], folder: Path | None = None) -> None:
    """Save (or update) a draft: its details and exactly these documents. Supporting documents added during the
    review are kept."""
    path = _folder(case_id, folder)
    stored = path / "documents"
    stored.mkdir(parents=True, exist_ok=True)
    for document in documents:
        target = stored / document.fingerprint
        if not target.exists():
            target.write_bytes(document.data)
    case_json = path / "case.json"
    earlier = json.loads(case_json.read_text()) if case_json.exists() else {}
    supporting = earlier.get("supporting", [])
    owner = details.get("owner", "").strip() or earlier.get("details", {}).get("owner", "")  # blank keeps the owner
    keep = {d.fingerprint for d in documents} | {s["sha256"] for s in supporting}
    for old in stored.iterdir():
        if old.name not in keep:
            old.unlink()  # a document removed from the review
    record = {
        "details": {**{field: details.get(field, "") for field in DETAIL_FIELDS}, "owner": owner.strip()},
        "documents": [{"name": d.name, "media_type": d.media_type, "sha256": d.fingerprint,
                       "description": d.description} for d in documents],
        "supporting": supporting,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    temporary = path / "case.json.tmp"
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path / "case.json")  # write in one go, so a half-written file is never left behind


def load_case(case_id: str, folder: Path | None = None) -> tuple[dict, list[UploadedDocument]]:
    """A draft's details and documents."""
    path = _folder(case_id, folder)
    record = json.loads((path / "case.json").read_text())
    documents = [
        UploadedDocument(d["name"], (path / "documents" / d["sha256"]).read_bytes(), d["media_type"],
                         d.get("description", ""))
        for d in record["documents"]
    ]
    return record["details"], documents


REVIEW_ID_PREFIX = "CLR-"


def review_id(case_id: str) -> str:
    """The review's ID for people to type, e.g. CLR-E9BD2CD5. It never changes, however often the review is saved."""
    return REVIEW_ID_PREFIX + case_id.split("-")[-1].upper()


def latest_reviews(folder: Path | None = None) -> list[dict]:
    """One saved review per legal entity (its most recent), most recently saved first. This is what people see."""
    seen, reviews = set(), []
    for draft in list_cases(folder):
        key = draft["entity_key"] or draft["id"]  # a review with no name or number stands on its own
        if key not in seen:
            seen.add(key)
            reviews.append(draft)
    return reviews


def remove_duplicates(folder: Path | None = None) -> list[str]:
    """Delete older saved reviews of an entity that has a newer one. Returns the ids removed."""
    keep = {d["id"] for d in latest_reviews(folder)}
    removed = [d["id"] for d in list_cases(folder) if d["id"] not in keep]
    for case_id in removed:
        shutil.rmtree(_folder(case_id, folder))
    return removed


def find_by_review_id(text: str, folder: Path | None = None) -> str | None:
    """The saved review with this ID (typed with or without CLR-, in any capitals), or None if there isn't one.
    A periodic review's ID (e.g. CLR-9580685D-PR1) finds the assessment it belongs to."""
    wanted = "".join(text.split()).upper().removeprefix(REVIEW_ID_PREFIX.upper()).removeprefix("CLR")
    wanted = wanted.split("-PR")[0]
    for draft in list_cases(folder):
        if review_id(draft["id"]) == REVIEW_ID_PREFIX + wanted:
            return draft["id"]
    return None


def entity_key(details: dict) -> str:
    """What identifies the legal entity: its company number, or else its name ("" if neither is given)."""
    number = parse_company_number(details.get("company_link", ""))
    if number:
        return f"company:{number}"
    name = normalise_company_name(details.get("entity_name", ""))
    return f"name:{name}" if name else ""


def find_case(details: dict, folder: Path | None = None) -> dict | None:
    """The saved review for this legal entity, if there is one (the most recent, if older duplicates exist)."""
    key = entity_key(details)
    matches = [d for d in list_cases(folder) if key and d["entity_key"] == key]
    return matches[0] if matches else None


def save_review(case_id: str | None, details: dict, documents: list[UploadedDocument],
                folder: Path | None = None) -> str:
    """Save the review, keeping one review per legal entity: it replaces any other saved review for the same entity.

    Returns the review's id: the one given, else the entity's existing review, else a new one.
    """
    key = entity_key(details)
    same_entity = [d["id"] for d in list_cases(folder) if key and d["entity_key"] == key]
    case_id = case_id or (same_entity[0] if same_entity else new_case_id())
    save_case(case_id, details, documents, folder)
    for other in same_entity:
        if other != case_id:
            shutil.rmtree(_folder(other, folder))  # an older review of the same entity, now replaced
    return case_id


def list_cases(folder: Path | None = None) -> list[dict]:
    """Every saved draft, most recently saved first: id, entity name, company, number of documents, saved at."""
    drafts = []
    for case_file in (folder or CASES_DIR).glob("*/case.json"):
        record = json.loads(case_file.read_text())
        drafts.append({
            "id": case_file.parent.name,
            "review_id": review_id(case_file.parent.name),
            "entity_name": record["details"].get("entity_name", ""),
            "entity_key": entity_key(record["details"]),
            "company_link": record["details"].get("company_link", ""),
            "owner": record["details"].get("owner", ""),
            "documents": len(record["documents"]),
            "saved_at": record["saved_at"],
        })
    return sorted(drafts, key=lambda d: d["saved_at"], reverse=True)


def answer_paths(case_id: str, folder: Path | None = None) -> dict[str, Path]:
    """Where a draft keeps Claude's answers, so reopening it with the same documents costs nothing."""
    path = _folder(case_id, folder)
    return {kind: path / f"{kind}.answer.json" for kind in ("labels", "industry", "assessment", "risk")}


def save_progress(case_id: str, pack_key: str, labels: list[DocumentLabel] | None, choice: tuple[str, str] | None,
                  folder: Path | None = None, comments: dict[str, str] | None = None) -> None:
    """Keep the reviewer's label corrections and industry and checklist choice with the draft.

    pack_key is the fingerprint of the documents they apply to; they are dropped if the documents change.
    """
    path = _folder(case_id, folder)
    path.mkdir(parents=True, exist_ok=True)
    record = {
        "pack_key": pack_key,
        "labels": [[label.name, label.document_type, label.reason] for label in labels or []],
        "choice": list(choice) if choice else None,
        "comments": comments or {},
    }
    temporary = path / "progress.json.tmp"
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path / "progress.json")


def load_progress(case_id: str, folder: Path | None = None) -> dict:
    """The saved label corrections and industry choice: {"pack_key", "labels", "choice"}, or {} if none."""
    path = _folder(case_id, folder) / "progress.json"
    if not path.exists():
        return {}
    record = json.loads(path.read_text())
    return {
        "pack_key": record["pack_key"],
        "labels": [DocumentLabel(*item) for item in record["labels"]],
        "choice": tuple(record["choice"]) if record["choice"] else None,
        "comments": record.get("comments", {}),
    }


def add_supporting_document(case_id: str, document: UploadedDocument, check_id: str, added_by: str = "",
                            folder: Path | None = None, verdict: str = "", verdict_finding: str = "",
                            description: str = "") -> None:
    """Add a document uploaded during the review (to back up a checklist line) to the review's document store."""
    path = _folder(case_id, folder)
    record = json.loads((path / "case.json").read_text())
    (path / "documents").mkdir(exist_ok=True)
    (path / "documents" / document.fingerprint).write_bytes(document.data)
    supporting = [s for s in record.get("supporting", []) if s["sha256"] != document.fingerprint]
    supporting.append({"name": document.name, "media_type": document.media_type, "sha256": document.fingerprint,
                       "check_id": check_id, "added_by": added_by.strip(),
                       "added_on": datetime.now().date().isoformat(),
                       "verdict": verdict, "verdict_finding": verdict_finding, "description": description.strip()})
    record["supporting"] = supporting
    temporary = path / "case.json.tmp"
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path / "case.json")


def load_supporting(case_id: str, folder: Path | None = None) -> list[tuple[UploadedDocument, dict]]:
    """Documents added during the review, each with its record: the check it supports, who added it and when."""
    path = _folder(case_id, folder)
    if not (path / "case.json").exists():
        return []
    record = json.loads((path / "case.json").read_text())
    return [(UploadedDocument(s["name"], (path / "documents" / s["sha256"]).read_bytes(), s["media_type"]), s)
            for s in record.get("supporting", [])]


def remove_supporting_document(case_id: str, sha256: str, folder: Path | None = None) -> None:
    """Delete a supporting document from the review's document store."""
    path = _folder(case_id, folder)
    record = json.loads((path / "case.json").read_text())
    record["supporting"] = [s for s in record.get("supporting", []) if s["sha256"] != sha256]
    still_used = {d["sha256"] for d in record["documents"]}
    if sha256 not in still_used:
        (path / "documents" / sha256).unlink(missing_ok=True)
    temporary = path / "case.json.tmp"
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path / "case.json")
