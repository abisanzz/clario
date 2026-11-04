import io
import zipfile

import pytest
from openpyxl import Workbook

from services.conversion import DOCX, EMAIL, HTML, XLSX, CannotRead, csv_rows, media_type_for, sheets, to_text
from services.pack import UnsupportedFile, UploadedDocument, numbered_files

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def word_file() -> bytes:
    """A small .docx: a heading, a paragraph and a table."""
    body = (f'<w:document {W}><w:body>'
            '<w:p><w:r><w:t>Register of members</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>EXAMPLE PAYMENTS </w:t></w:r><w:r><w:t>LTD</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Alex Sample</w:t></w:r></w:p></w:tc>'
            '<w:tc><w:p><w:r><w:t>60%</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '</w:body></w:document>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", body)
    return buffer.getvalue()


def excel_file() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Shareholders"
    sheet.append(["Name", "Holding"])
    sheet.append(["Alex Sample", 0.6])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_file_types_come_from_the_name():
    assert media_type_for("Register.DOCX", "application/octet-stream") == DOCX
    assert media_type_for("accounts.xlsx") == XLSX
    assert media_type_for("scan.pdf", "") == "application/pdf"
    assert media_type_for("photo.JPG") == "image/jpeg"


def test_word_documents_keep_their_paragraphs_and_tables():
    assert to_text("register.docx", word_file(), DOCX) == "Register of members\nEXAMPLE PAYMENTS LTD\nAlex Sample | 60%"


def test_excel_workbooks_keep_every_sheet():
    assert sheets(excel_file()) == [("Shareholders", [["Name", "Holding"], ["Alex Sample", "0.6"]])]
    assert to_text("holdings.xlsx", excel_file(), XLSX).startswith("Sheet: Shareholders\nName\tHolding")


def test_emails_web_pages_and_csv():
    message = (b"From: client@example.com\r\nTo: kyc@example.com\r\nSubject: Proof of address\r\n"
               b"Content-Type: text/plain; charset=utf-8\r\n\r\nPlease find the bill attached.\r\n")
    text = to_text("reply.eml", message, EMAIL)
    assert "Subject: Proof of address" in text and "Please find the bill attached." in text
    page = b"<html><head><style>p{}</style></head><body><h1>About us</h1><p>We provide payments.</p></body></html>"
    assert to_text("about.html", page, HTML) == "About us\nWe provide payments."
    assert csv_rows(b"name,share\nAlex Sample,60%\n") == [["name", "share"], ["Alex Sample", "60%"]]


def test_old_office_files_and_broken_files_get_a_clear_message():
    with pytest.raises(CannotRead, match="Save it as .docx"):
        to_text("old.doc", b"binary", "application/msword")
    with pytest.raises(CannotRead, match="could not be read"):
        to_text("broken.docx", b"not a zip", DOCX)


def test_converted_documents_are_sent_as_labelled_text():
    content = numbered_files([UploadedDocument("register.docx", word_file(), DOCX)])
    assert content[0] == {"type": "text", "text": "File 1: register.docx"}
    assert content[1]["source"] == {"type": "text", "media_type": "text/plain",
                                    "data": "Register of members\nEXAMPLE PAYMENTS LTD\nAlex Sample | 60%"}
    assert content[1]["title"] == "register.docx"
    with pytest.raises(UnsupportedFile, match="no text was found"):
        numbered_files([UploadedDocument("empty.txt", b"   ", "text/plain")])
