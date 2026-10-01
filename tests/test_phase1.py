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


def test_comparison_marks_original_red_and_replacement_green(tmp_path):
    source = tmp_path / 'highlight-source.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=160)
        page.insert_text((40, 70), 'De redacteur bedoeld dat.', fontsize=14)
        doc.save(source)
    output = tmp_path / 'highlights.pdf'
    build_comparison_pdf_preview(source, 'De redacteur bedoelt dat.', output)
    with fitz.open(output) as doc:
        page = doc[0]
        left = page.get_text(clip=fitz.Rect(0, 0, 400, 160))
        right = page.get_text(clip=fitz.Rect(420, 0, 820, 160))
        assert 'bedoeld' in left
        assert 'bedoelt' in right
        assert 'bedoeld' not in right
        assert 'De redacteur' in right
        pix = page.get_pixmap()
        old_rect = page.search_for('bedoeld')[0]
        new_rect = page.search_for('bedoelt')[0]
        r, g, b = pix.pixel(int(old_rect.x0 + 2), int(old_rect.y0 + 1))[:3]
        assert r > g + 20 and r > b + 20
        r, g, b = pix.pixel(int(new_rect.x0 + 2), int(new_rect.y0 + 1))[:3]
        assert g > r + 20 and g > b + 20


def test_comparison_preserves_case_and_punctuation_corrections(tmp_path):
    source = tmp_path / 'case-source.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 70), 'hallo wereld!')
        doc.save(source)
    output = tmp_path / 'case.pdf'
    build_comparison_pdf_preview(source, 'Hallo wereld.', output)
    with fitz.open(output) as doc:
        right = doc[0].get_text(clip=fitz.Rect(615, 0, 1210, 842))
        assert 'Hallo wereld.' in right


def test_pdf_upload_keeps_review_chunks_on_page_boundaries(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    monkeypatch.setattr(LanguageToolClient, '_request_chunk', lambda self, text, language: [])
    with fitz.open() as doc:
        for text in ['Eerste pagina. ' * 1400, '', 'Laatste pagina.']:
            page = doc.new_page(width=600, height=20000)
            if text:
                page.insert_textbox(page.rect, text, fontsize=10)
        response = TestClient(app).post('/upload', files={'file': ('pages.pdf', doc.tobytes(), 'application/pdf')})
    assert response.status_code == 200
    chunks = response.json()['chunks']
    assert len(chunks) == 3
    assert len(chunks[0]['text']) > 15000
    assert [chunk['page_index'] for chunk in chunks] == [0, 1, 2]
    assert chunks[1]['text'] == ''
    assert chunks[2]['text'] == 'Laatste pagina.'
    assert chunks[2]['start'] == len(chunks[0]['text']) + 2


def test_languagetool_chunk_offsets_preserve_whitespace(monkeypatch):
    client = LanguageToolClient('http://unused', max_chars_per_request=18)
    text = '  Een regel.\n\nNog  een fout. ' + 'x' * 40
    monkeypatch.setattr(client, '_request_chunk', lambda chunk, language: [
        {'offset': chunk.index('fout'), 'length': 4}
    ] if 'fout' in chunk else [])
    chunks = client.check_document_chunks(text)
    assert ''.join(chunk['text'] for chunk in chunks) == text
    assert all(len(chunk['text']) <= 18 for chunk in chunks)
    issue = next(issue for chunk in chunks for issue in chunk['issues'])
    assert issue['offset'] == text.index('fout')


def test_comparison_rejects_partial_page_text(sample_pdf_file, tmp_path):
    with pytest.raises(ValueError, match='volledige PDF-pagina'):
        build_comparison_pdf_preview(sample_pdf_file, 'bedoelt', tmp_path / 'bad.pdf', original_text='bedoeld')
    assert not (tmp_path / 'bad.pdf').exists()


def test_unchanged_multicolumn_page_keeps_all_text(tmp_path):
    from app.parsers.pdf_parser import page_text
    source = tmp_path / 'columns.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        # PDF content order deliberately differs from visual reading order.
        page.insert_text((300, 100), 'Rechter kolom blijft staan.')
        page.insert_text((40, 100), 'Linker kolom blijft ook staan.')
        page.insert_text((40, 50), 'Koptekst')
        original = page_text(page)
        doc.save(source)
    output = tmp_path / 'unchanged.pdf'
    build_comparison_pdf_preview(source, original, output, original_text=original)
    with fitz.open(output) as doc:
        page = doc[0]
        left = page.get_text(clip=fitz.Rect(0, 0, 595, 842))
        right = page.get_text(clip=fitz.Rect(615, 0, 1210, 842))
        assert left == right
        assert not page.get_drawings()


def test_comparison_api_rejects_stale_review_text(sample_pdf_file, tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    monkeypatch.setattr(main, 'TEMP_DIR', tmp_path)
    response = TestClient(app).post('/comparison-pdf', json={
        'stored_name': sample_pdf_file.name,
        'original_text': 'Een deel van een andere pagina.',
        'revised_text': 'Een aangepast deel.',
        'page_index': 0,
    })
    assert response.status_code == 409
    assert 'Upload het document opnieuw' in response.json()['detail']
