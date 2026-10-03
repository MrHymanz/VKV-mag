from pathlib import Path
from io import BytesIO
from fontTools.ttLib import TTFont

import fitz
import reportlab
from fastapi.testclient import TestClient

import app.main as main
import app.services.pdf_text_style as styles


def test_postscript_name_preserves_caps_variant():
    data = (Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf').read_bytes()
    font = TTFont(BytesIO(data))
    for record in font['name'].names:
        if record.nameID in (1, 2, 4, 6):
            value = {1: 'Meta', 2: 'Book', 4: 'Meta Book Caps', 6: 'MetaBook-Caps'}[record.nameID]
            record.string = value.encode(record.getEncoding())
    buffer = BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    assert styles.font_matches(data, 'MetaBook-Caps', 'Meta Book')
    assert not styles.font_matches(data, 'MetaBook', 'Meta Book')
    assert not styles.font_matches(data, 'MetaBold-Caps', 'Meta Book')


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


def test_explicit_override_persists_and_supplies_requested_font(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'FONT_DIR', tmp_path)
    monkeypatch.setattr(styles, 'FONT_DIR', tmp_path)
    data = (Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf').read_bytes()
    client = TestClient(main.app)
    response = client.post('/fonts/upload', data={'expected_font': 'Different-Caps', 'override': 'true'},
                           files={'file': ('test.ttf', data)})
    assert response.status_code == 200
    assert response.json()['override'] is True
    with fitz.open() as doc:
        page = doc.new_page()
        typography = styles.PageTypography(page)
        assert typography.supplemental_face('Different-Caps', 'N') is not None
        assert typography.supplemental_face('Other-Font', 'N') is None


def test_comparison_missing_font_reports_source_page_and_correction(monkeypatch):
    from app.services.pdf_preview import _comparison_pages
    def missing(self, name, text):
        raise self.missing_font('Missing-Font')
    monkeypatch.setattr(styles.PageTypography, 'supplemental_face', missing)
    monkeypatch.setattr(styles.PageTypography, 'original_face',
                        lambda self, glyph: missing(self, '', ''))
    with fitz.open() as doc:
        for i in range(3):
            doc.new_page().insert_text((40, 70), 'test')
        try:
            _comparison_pages(doc, 2, 'Test')
        except styles.MissingFontError as exc:
            assert 'pagina/deel 3' in str(exc)
            assert '“test” → “Test”' in str(exc)
        else:
            raise AssertionError('Expected missing font')
