from pathlib import Path

import fitz
import reportlab
from fastapi.testclient import TestClient

import app.main as main
import app.services.pdf_text_style as styles


def test_font_upload_validates_and_enables_original_font(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'FONT_DIR', tmp_path)
    monkeypatch.setattr(styles, 'FONT_DIR', tmp_path)
    data = (Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf').read_bytes()
    font = fitz.Font(fontbuffer=data)
    client = TestClient(main.app)
    for content, expected in [(b'not a font', font.name), (data, 'MetaBook-Caps')]:
        response = client.post('/fonts/upload', data={'expected_font': expected},
                               files={'file': ('font.ttf', content)})
        assert response.status_code == 400
        assert not list(tmp_path.iterdir())
    response = client.post('/fonts/upload', data={'expected_font': font.name},
                           files={'file': ('../../font.ttf', data)})
    assert response.status_code == 200
    assert len(list(tmp_path.iterdir())) == 1
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 50), 'Nieuw')
        typography = styles.PageTypography(page)
        glyph = typography.glyphs(typography.words[0])[0]
        glyph.span['font'] = font.name
        assert typography.original_face(glyph).font.name == font.name


def test_missing_font_response_identifies_required_font(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'TEMP_DIR', tmp_path)
    def missing(*args, **kwargs):
        raise styles.MissingFontError('MetaBook-Caps')
    monkeypatch.setattr(main, 'build_comparison_pdf_preview', missing)
    response = TestClient(main.app).post('/comparison-pdf', json={'original_text': 'tekst'})
    assert response.status_code == 409
    assert response.headers['X-Missing-Font'] == 'MetaBook-Caps'
