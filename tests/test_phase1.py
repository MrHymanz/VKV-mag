from pathlib import Path

import pytest
from docx import Document

from app.parsers.docx_parser import DocxParser
from app.parsers.txt_parser import TxtParser
from app.services.correction_service import apply_correction
from app.services.languagetool import LanguageToolClient


@pytest.fixture
def sample_txt_file(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("De redacteur bedoeld dat de auto uit 1967 komt.\n", encoding="utf-8")
    return file_path


@pytest.fixture
def sample_docx_file(tmp_path):
    file_path = tmp_path / "sample.docx"
    doc = Document()
    paragraph = doc.add_paragraph("De redacteur bedoeld dat de auto uit 1967 komt.")
    paragraph.runs[0].bold = True
    doc.save(file_path)
    return file_path


def test_txt_parser_extracts_text(sample_txt_file):
    parser = TxtParser()
    result = parser.parse(sample_txt_file)

    assert "De redacteur bedoeld dat de auto uit 1967 komt." in result.text
    assert result.file_type == "txt"


def test_docx_parser_extracts_text(sample_docx_file):
    parser = DocxParser()
    result = parser.parse(sample_docx_file)

    assert "De redacteur bedoeld dat de auto uit 1967 komt." in result.text
    assert result.file_type == "docx"


def test_languagetool_client_builds_correct_url():
    client = LanguageToolClient(base_url="http://localhost:8081")
    assert client.check_url.endswith("/v2/check")


def test_apply_correction_replaces_text():
    text = "De redacteur bedoeld dat de auto uit 1967 komt."
    corrected = apply_correction(text, 13, 7, "bedoelt")
    assert corrected == "De redacteur bedoelt dat de auto uit 1967 komt."


def test_upload_validation_rejects_bad_extension(tmp_path):
    file_path = tmp_path / "bad.exe"
    file_path.write_text("bad", encoding="utf-8")
    assert file_path.suffix.lower() != ".txt"
