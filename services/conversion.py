"""Documents that are not PDFs or images (Word, Excel, CSV, text, emails, web pages), turned into text so Clario AI
can read them. Uses only Python's own tools and openpyxl, which Clario already needs.

Old binary Office files (.doc, .xls) cannot be read this way; they need saving as .docx, .xlsx or PDF.
"""

import csv
import email
import io
import zipfile
from email import policy
from html.parser import HTMLParser
from pathlib import PurePath
from xml.etree import ElementTree

from openpyxl import load_workbook

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV, TEXT, MARKDOWN, HTML, EMAIL = "text/csv", "text/plain", "text/markdown", "text/html", "message/rfc822"

# What each file extension is, for the types read as text
TEXT_TYPES = {".docx": DOCX, ".xlsx": XLSX, ".csv": CSV, ".txt": TEXT, ".md": MARKDOWN, ".html": HTML,
              ".htm": HTML, ".eml": EMAIL}
FILE_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp", ".gif": "image/gif"} | TEXT_TYPES
UPLOAD_EXTENSIONS = [extension.lstrip(".") for extension in FILE_TYPES]  # what the upload boxes accept
NOT_READABLE = {".doc": "Word 97-2003", ".xls": "Excel 97-2003", ".ppt": "PowerPoint 97-2003"}

WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class CannotRead(ValueError):
    """A file that cannot be turned into text."""


def media_type_for(name: str, given: str = "") -> str:
    """The file's type, worked out from its name (browsers report Office files inconsistently)."""
    return FILE_TYPES.get(PurePath(name).suffix.lower(), given or "application/octet-stream")


def is_text_type(media_type: str) -> bool:
    return media_type in TEXT_TYPES.values()


def to_text(name: str, data: bytes, media_type: str) -> str:
    """The document's content as plain text."""
    suffix = PurePath(name).suffix.lower()
    if suffix in NOT_READABLE:
        raise CannotRead(f"{name}: {NOT_READABLE[suffix]} files can't be read. Save it as .docx, .xlsx or PDF.")
    try:
        if media_type == DOCX:
            return _word(data)
        if media_type == XLSX:
            return "\n\n".join(f"Sheet: {sheet}\n" + "\n".join("\t".join(row) for row in rows)
                               for sheet, rows in sheets(data))
        if media_type == EMAIL:
            return _email(data)
        if media_type == HTML:
            return _html(_decode(data))
        if media_type in (CSV, TEXT, MARKDOWN):
            return _decode(data)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, ValueError, OSError) as error:
        raise CannotRead(f"{name}: the file could not be read ({error})") from error
    raise CannotRead(f"{name}: this type of file can't be read")


def sheets(data: bytes) -> list[tuple[str, list[list[str]]]]:
    """Each sheet of an Excel workbook, as rows of cell text (empty rows left out)."""
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        return [(sheet.title, [["" if cell is None else str(cell) for cell in row]
                               for row in sheet.iter_rows(values_only=True) if any(c is not None for c in row)])
                for sheet in workbook.worksheets]
    finally:
        workbook.close()


def csv_rows(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(_decode(data))))


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _word(data: bytes) -> str:
    """Paragraphs and tables of a .docx, in order. Table cells are separated by " | "."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        body = ElementTree.fromstring(archive.read("word/document.xml")).find(f"{WORD}body")
    lines = []
    for block in body if body is not None else []:
        if block.tag == f"{WORD}p":
            lines.append(_paragraph(block))
        elif block.tag == f"{WORD}tbl":
            for row in block.iter(f"{WORD}tr"):
                cells = [" ".join(_paragraph(p) for p in cell.iter(f"{WORD}p")).strip()
                         for cell in row.iter(f"{WORD}tc")]
                lines.append(" | ".join(cells))
    return "\n".join(lines).strip()


def _paragraph(paragraph) -> str:
    parts = []
    for node in paragraph.iter():
        if node.tag == f"{WORD}t" and node.text:
            parts.append(node.text)
        elif node.tag in (f"{WORD}tab",):
            parts.append("\t")
        elif node.tag in (f"{WORD}br", f"{WORD}cr"):
            parts.append("\n")
    return "".join(parts)


def _email(data: bytes) -> str:
    message = email.message_from_bytes(data, policy=policy.default)
    header = "\n".join(f"{field}: {message[field]}" for field in ("From", "To", "Date", "Subject") if message[field])
    body = message.get_body(preferencelist=("plain", "html"))
    text = ""
    if body is not None:
        content = body.get_content()
        text = _html(content) if body.get_content_type() == "text/html" else content
    attachments = [part.get_filename() for part in message.iter_attachments() if part.get_filename()]
    return (header + "\n\n" + text.strip()
            + (f"\n\nAttachments (not read): {', '.join(attachments)}" if attachments else "")).strip()


class _TextOnly(HTMLParser):
    SKIP = {"script", "style", "head"}
    BREAKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}

    def __init__(self):
        super().__init__()
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def _html(markup: str) -> str:
    parser = _TextOnly()
    parser.feed(markup)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)
