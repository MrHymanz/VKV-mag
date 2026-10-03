import fitz
import pytest
from types import SimpleNamespace

from app.parsers.pdf_parser import page_text
from app.services.pdf_preview import apply_pdf_page_corrections, _comparison_pages
from app.services.pdf_text_style import PageTypography


def test_missing_letter_uses_matching_full_font(tmp_path, monkeypatch):
    import app.services.pdf_text_style as styles
    full = fitz.Font(fontbuffer=fitz.Font('hebi').buffer)
    (tmp_path / 'editorial.otf').write_bytes(full.buffer)
    monkeypatch.setattr(styles, 'FONT_DIR', tmp_path)
    with fitz.open() as doc:
        page = doc.new_page()
        typography = PageTypography(page)
        monkeypatch.setattr(typography, 'original_face', lambda glyph:
                            SimpleNamespace(font=SimpleNamespace(has_glyph=lambda code: 0)))
        glyph = SimpleNamespace(span={'font': full.name})
        face = typography.face_for(glyph, 'N')
        assert face.font.name == full.name
        assert face.font.has_glyph(ord('N'))
        # A different weight must not silently use the available bold italic.
        glyph.span['font'] = 'Helvetica'
        with pytest.raises(ValueError, match='niet volledig beschikbaar'):
            typography.face_for(glyph, 'N')


def word_style(page, text):
    typography = PageTypography(page)
    word = next(word for word in typography.words if word[4] == text)
    return typography.glyphs(word)


@pytest.mark.parametrize('angle', [0.077584, -0.077584, 3, -3])
def test_slightly_rotated_text_preserves_angle_style_and_baseline(angle):
    with fitz.open() as doc:
        page = doc.new_page()
        origin = fitz.Point(100, 150)
        page.insert_text(origin, 'APK controle', fontsize=14, fontname='hebo',
                         color=(0.7, 0.3, 0.1), morph=(origin, fitz.Matrix(angle)))
        before = word_style(page, 'APK')[0]
        apply_pdf_page_corrections(page, 'apk controle')
        after = word_style(page, 'apk')[0]
        assert after.direction == pytest.approx(before.direction, abs=0.00002)
        assert after.origin.x == pytest.approx(before.origin.x, abs=0.01)
        assert after.origin.y == pytest.approx(before.origin.y, abs=0.01)
        assert after.span['font'] == before.span['font']
        assert after.span['color'] == before.span['color']
        assert after.span['size'] == pytest.approx(before.span['size'], abs=0.005)
        assert 'APK' not in page.get_text()
        assert 'controle' in page.get_text()


@pytest.mark.parametrize('font', ['helv', 'hebi', 'tibi'])
def test_embedded_font_weight_size_color_opacity_and_baseline_preserved(font):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_font(fontname='Original', fontbuffer=fitz.Font(font).buffer)
        page.insert_text((40, 70), 'Indian Summer PR', fontname='Original', fontsize=14,
                         color=(0.72, 0.31, 0.09), fill_opacity=0.7,
                         morph=(fitz.Point(40, 70), fitz.Matrix(0.97, 1.03)))
        before = word_style(page, 'Summer')
        apply_pdf_page_corrections(page, 'Indian summer pr')
        after = word_style(page, 'summer')
        for glyph in after:
            assert glyph.span['font'] == before[0].span['font']
            assert glyph.span['flags'] == before[0].span['flags']
            assert glyph.span['size'] == pytest.approx(before[0].span['size'], abs=0.003)
            assert glyph.span['color'] == before[0].span['color']
            assert glyph.span['alpha'] == pytest.approx(before[0].span['alpha'], abs=1)
            assert glyph.origin.y == pytest.approx(before[0].origin.y, abs=0.01)
        assert after[0].origin.x == pytest.approx(before[0].origin.x, abs=0.01)
        assert word_style(page, 'pr')[0].span['font'] == before[0].span['font']


def test_original_letter_spacing_preserved():
    with fitz.open() as doc:
        page = doc.new_page()
        font = fitz.Font('helv')
        x = 40
        for char in 'SUMMER':
            page.insert_text((x, 70), char, fontsize=14, fontname='helv')
            x += font.text_length(char, fontsize=14) + 0.3
        apply_pdf_page_corrections(page, 'summer')
        glyphs = word_style(page, 'summer')
        for left, right in zip(glyphs, glyphs[1:]):
            assert right.origin.x - left.rect.x1 == pytest.approx(0.3, abs=0.02)


def test_added_comma_keeps_color_size_and_space_before_next_word():
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 70), 'klassieker maar', fontsize=18, color=(1, 0.5, 0))
        before = word_style(page, 'klassieker')
        before_next = word_style(page, 'maar')
        old_gap = before_next[0].origin.x - before[-1].rect.x1
        apply_pdf_page_corrections(page, 'klassieker, maar')
        corrected = word_style(page, 'klassieker,')
        following = word_style(page, 'maar')
        assert corrected[-1].span['color'] == before[0].span['color']
        assert corrected[-1].span['size'] == pytest.approx(18, abs=0.003)
        assert following[0].origin.x - corrected[-1].rect.x1 == pytest.approx(old_gap, abs=0.02)
        assert following[0].origin.y == pytest.approx(before_next[0].origin.y, abs=0.01)


def test_image_blocks_do_not_change_style_lookup():
    with fitz.open() as doc:
        page = doc.new_page()
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4))
        image.clear_with(255)
        page.insert_image(fitz.Rect(20, 20, 40, 40), pixmap=image)
        page.insert_text((40, 90), 'PR', fontsize=16, fontname='tibi', color=(0.2, 0.4, 0.6))
        before = word_style(page, 'PR')[0]
        apply_pdf_page_corrections(page, 'pr')
        after = word_style(page, 'pr')[0]
        assert after.span['font'] == before.span['font']
        assert after.span['color'] == before.span['color']
        assert after.span['size'] == pytest.approx(16, abs=0.003)
        assert len(page.get_images()) == 1


def test_mixed_fonts_in_one_word_are_preserved():
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 70), 'fo', fontsize=14, fontname='hebo')
        x = 40 + fitz.Font('hebo').text_length('fo', fontsize=14)
        page.insert_text((x, 70), 'utt', fontsize=14, fontname='helv')
        apply_pdf_page_corrections(page, 'fout')
        result = word_style(page, 'fout')
        assert result[0].span['font'] == 'Helvetica-Bold'
        assert result[-1].span['font'] == 'Helvetica'


def test_long_correction_is_rejected_before_page_is_modified():
    with fitz.open() as doc:
        page = doc.new_page(width=120, height=150)
        page.insert_text((40, 70), 'kort einde', fontsize=12)
        original = page_text(page)
        with pytest.raises(ValueError, match='oorspronkelijke lettergrootte'):
            apply_pdf_page_corrections(page, 'onwaarschijnlijklangwoord einde')
        assert page_text(page) == original
        assert not list(page.annots() or [])


def test_comparison_changes_highlight_not_letter_color():
    with fitz.open() as source:
        page = source.new_page()
        page.insert_text((40, 70), 'Summer', fontsize=18, color=(0.9, 0.4, 0.1))
        before = word_style(page, 'Summer')[0]
        left, right = _comparison_pages(source, 0, 'summer')
        try:
            result = word_style(right[0], 'summer')[0]
            assert result.span['color'] == before.span['color']
            assert result.span['size'] == pytest.approx(before.span['size'], abs=0.003)
            assert right[0].get_drawings()
        finally:
            left.close()
            right.close()
