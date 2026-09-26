from pathlib import Path

import fitz
import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.parsers.docx_parser import DocxParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.txt_parser import TxtParser
from app.services.correction_service import apply_correction
from app.services.languagetool import LanguageToolClient
from app.services.pdf_preview import build_comparison_pdf_preview


@pytest.fixture
def sample_txt_file(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("De redacteur bedoeld dat de auto uit 1967 komt.\n", encoding="utf-8")
    return file_path


@pytest.fixture
def sample_pdf_file(tmp_path):
    file_path = tmp_path / "sample.pdf"
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(file_path), pagesize=letter)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 720, "De redacteur bedoeld dat de auto uit 1967 komt.")
    pdf.save()
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


def test_pdf_parser_extracts_text(sample_pdf_file):
    parser = PdfParser()
    result = parser.parse(sample_pdf_file)

    assert "De redacteur bedoeld dat de auto uit 1967 komt." in result.text
    assert result.file_type == "pdf"


def test_languagetool_client_builds_correct_url():
    client = LanguageToolClient(base_url="http://localhost:8081")
    assert client.check_url.endswith("/v2/check")


def test_languagetool_client_posts_form_data(monkeypatch):
    captured = []

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"matches": []}

    def fake_post(url, data=None, timeout=None, headers=None):
        captured.append({
            "url": url,
            "data": data,
            "headers": headers,
            "timeout": timeout,
        })
        return DummyResponse()

    monkeypatch.setattr("app.services.languagetool.httpx.post", fake_post)

    client = LanguageToolClient(base_url="http://localhost:8010")
    assert client.check_text("Hallo wereld", language="nl-NL") == []
    assert captured[0]["url"].endswith("/v2/check")
    assert captured[0]["data"]["text"] == "Hallo wereld"
    assert captured[0]["data"]["language"] == "nl-NL"
    assert captured[0]["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_languagetool_client_splits_large_text(monkeypatch):
    captured = []

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"matches": []}

    def fake_post(url, data=None, timeout=None, headers=None):
        captured.append(data["text"])
        return DummyResponse()

    monkeypatch.setattr("app.services.languagetool.httpx.post", fake_post)

    client = LanguageToolClient(base_url="http://localhost:8010", max_chars_per_request=50)
    long_text = "Hallo wereld. " * 20
    assert client.check_text(long_text, language="nl-NL") == []
    assert len(captured) > 1
    assert all(len(chunk) <= 50 for chunk in captured)


def test_approve_chunk_persists_state():
    client = TestClient(app)
    file_content = b"Hallo wereld. Dit is een test."

    response = client.post("/upload", files={"file": ("sample.txt", file_content, "text/plain")})
    assert response.status_code == 200
    payload = response.json()
    assert payload["chunks"]
    chunk_id = payload["chunks"][0]["id"]

    approval = client.post(
        "/approve-chunk",
        json={
            "stored_name": payload["stored_name"],
            "chunk_id": chunk_id,
            "approved": True,
        },
    )
    assert approval.status_code == 200
    assert approval.json()["approved"] is True


def test_apply_correction_replaces_text():
    text = "De redacteur bedoeld dat de auto uit 1967 komt."
    corrected = apply_correction(text, 13, 7, "bedoelt")
    assert corrected == "De redacteur bedoelt dat de auto uit 1967 komt."


def test_build_comparison_pdf_preview_creates_pdf(tmp_path):
    original = "Eerste regel.\nTweede regel.\n"
    revised = "Eerste regel.\nTweede regel aangepast.\n"
    output_path = tmp_path / "comparison-preview.pdf"

    build_comparison_pdf_preview(None, revised, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes().startswith(b"%PDF")


def test_build_comparison_pdf_preview_single_page_for_selected_page(tmp_path):
    pdf_path = tmp_path / "multi-page.pdf"
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    canvas_doc = canvas.Canvas(str(pdf_path), pagesize=letter)
    canvas_doc.drawString(100, 700, "Pagina 1")
    canvas_doc.showPage()
    canvas_doc.drawString(100, 700, "Pagina 2")
    canvas_doc.save()

    output_path = tmp_path / "selected-page-comparison.pdf"
    build_comparison_pdf_preview(pdf_path, "Aangepaste tekst voor pagina 2", output_path, page_index=1)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes().startswith(b"%PDF")


def test_build_comparison_pdf_preview_keeps_original_page_artwork(tmp_path):
    pdf_path = tmp_path / "layout-page.pdf"
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    canvas_doc = canvas.Canvas(str(pdf_path), pagesize=letter)
    canvas_doc.setFillColor(HexColor("#ff0000"))
    canvas_doc.rect(100, 450, 180, 150, fill=1, stroke=0)
    canvas_doc.setFillColor(HexColor("#000000"))
    canvas_doc.drawString(120, 520, "Logo layout test")
    canvas_doc.save()

    output_path = tmp_path / "artwork-comparison.pdf"
    build_comparison_pdf_preview(pdf_path, "Aangepaste tekst op dezelfde pagina", output_path)

    doc = fitz.open(str(output_path))
    assert len(doc) == 1
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
    width, height = pix.width, pix.height

    found_red = False
    for x in range(width // 2 + 30, width - 30):
        for y in range(120, 260):
            r, g, b = pix.pixel(x, y)[:3]
            if r > 180 and g < 120 and b < 120:
                found_red = True
                break
        if found_red:
            break

    assert found_red is True


def test_upload_validation_rejects_bad_extension(tmp_path):
    file_path = tmp_path / "bad.exe"
    file_path.write_text("bad", encoding="utf-8")
    assert file_path.suffix.lower() != ".txt"
