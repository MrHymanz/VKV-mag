from __future__ import annotations

import difflib
import re
from pathlib import Path

import fitz

from app.parsers.pdf_parser import page_text
from app.services.layout_protection import changes_word_break, overlaps_break


def _wrap_text_for_render(text: str, max_chars_per_line: int = 84) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars_per_line:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines or [""]


def _highlight(page: fitz.Page, rect: fitz.Rect, color: tuple[float, float, float]) -> None:
    page.draw_rect(rect, color=None, fill=color, fill_opacity=0.22, overlay=True)


def _comparison_pages(source_doc: fitz.Document, page_index: int, revised_text: str) -> tuple[fitz.Document, fitz.Document]:
    original = fitz.open()
    original.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
    revised = fitz.open()
    revised.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
    left, right = original[0], revised[0]
    words = left.get_text("words")
    # Preserve punctuation and capitalisation: those may themselves be corrections.
    tokens = re.findall(r"\S+", revised_text)
    matcher = difflib.SequenceMatcher(None, [word[4] for word in words], tokens, autojunk=False)
    source_text = " ".join(word[4] for word in words)
    offsets = []
    cursor = 0
    for word in words:
        offsets.append(cursor)
        cursor += len(word[4]) + 1
    replacements = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed = words[i1:i2]
        start = offsets[i1] if i1 < len(offsets) else len(source_text)
        end = offsets[i2 - 1] + len(words[i2 - 1][4]) if removed else start
        # Also protect requests from an older browser session: never redraw
        # editorial word breaks, even if the submitted text joins them.
        if overlaps_break(source_text, start, end) or changes_word_break(
            " ".join(word[4] for word in removed), " ".join(tokens[j1:j2])
        ):
            continue
        for word in removed:
            rect = fitz.Rect(word[:4])
            _highlight(left, rect, (1, 0.2, 0.2))
            # Remove only text, leaving pictures and background artwork intact.
            # Font bounding boxes can overlap neighbouring lines in magazines.
            # A narrow strip through the glyph centres avoids removing those lines.
            strip = fitz.Rect(rect.x0 + 0.1, rect.y0 + rect.height * 0.45,
                              rect.x1 - 0.1, rect.y0 + rect.height * 0.55)
            right.add_redact_annot(strip, fill=False, cross_out=False)
        added = tokens[j1:j2]
        if not added or not words:
            continue
        if removed:
            # Keep each source line separate for corrections spanning line breaks.
            groups = []
            for word in removed:
                if not groups or groups[-1][-1][5:7] != word[5:7]:
                    groups.append([])
                groups[-1].append(word)
            cursor = 0
            for index, group in enumerate(groups):
                count = len(added) - cursor if index == len(groups) - 1 else min(len(group), len(added) - cursor)
                if count <= 0:
                    break
                rect = fitz.Rect(group[0][:4])
                for word in group[1:]:
                    rect |= fitz.Rect(word[:4])
                replacements.append((rect, " ".join(added[cursor:cursor + count])))
                cursor += count
        else:
            # Insertions use the available gap, without painting over a neighbour.
            anchor = words[min(i1, len(words) - 1)]
            x0, y0, x1, y1 = anchor[:4]
            if i1 > 0 and words[i1 - 1][5:7] == anchor[5:7] and i1 < len(words):
                rect = fitz.Rect(words[i1 - 1][2] + 0.5, y0, x0 - 0.5, y1)
            elif i1 == 0:
                rect = fitz.Rect(max(0, x0 - 60), y0, x0 - 1, y1)
            else:
                rect = fitz.Rect(x1 + 1, y0, min(right.rect.width, x1 + 90), y1)
            if rect.width > 0:
                replacements.append((rect, " ".join(added)))
    right.apply_redactions(images=0, graphics=0)
    font = fitz.Font("helv")
    for rect, text in replacements:
        size = min(rect.height / (font.ascender - font.descender),
                   rect.width / max(font.text_length(text, fontsize=1), 0.01))
        _highlight(right, rect, (0.15, 0.85, 0.3))
        right.insert_text((rect.x0, rect.y0 + font.ascender * size), text,
                          fontsize=size, fontname="helv", color=(0.05, 0.25, 0.1))
    return original, revised


def build_comparison_pdf_preview(
    original_pdf_path: str | Path | None,
    revised_text: str,
    output_path: str | Path,
    page_index: int = 0,
    original_text: str | None = None,
) -> Path:
    output = Path(output_path)
    if original_pdf_path and Path(original_pdf_path).exists():
        source_doc = fitz.open(str(original_pdf_path))
        if not 0 <= page_index < len(source_doc):
            source_doc.close()
            raise ValueError("Deze PDF-pagina bestaat niet. Upload het document opnieuw.")
        target_page_index = page_index
        src_page = source_doc[target_page_index]
        if original_text is not None and original_text != page_text(src_page):
            source_doc.close()
            raise ValueError("De controletekst hoort niet bij deze volledige PDF-pagina. Upload het document opnieuw om per pagina te controleren.")
        page_rect = src_page.rect
        width = float(page_rect.width)
        height = float(page_rect.height)

        compare_doc = fitz.open()
        compare_page = compare_doc.new_page(width=width * 2 + 40, height=height)

        original, revised = _comparison_pages(source_doc, target_page_index, revised_text)
        if original[0].get_contents():
            compare_page.show_pdf_page(fitz.Rect(0, 0, width, height), original, 0)
        if revised[0].get_contents():
            compare_page.show_pdf_page(fitz.Rect(width + 20, 0, width * 2 + 20, height), revised, 0)
        original.close()
        revised.close()

        compare_doc.save(str(output))
        compare_doc.close()
        source_doc.close()
        return output

    # Fallback: pure text comparison as a last resort when no PDF is available.
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    left_x = 50
    right_x = width / 2 + 20
    top_y = height - 60

    pdf.setFillColor(colors.HexColor("#f3efe8"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)

    pdf.setStrokeColor(colors.HexColor("#d9d1c5"))
    pdf.setFillColor(colors.HexColor("#294461"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(left_x, height - 30, "ORIGINEEL")
    pdf.drawString(right_x, height - 30, "AANGEPAST")

    pdf.setStrokeColor(colors.HexColor("#d9d1c5"))
    pdf.line(width / 2, 40, width / 2, height - 50)

    text_lines = _wrap_text_for_render(revised_text)
    pdf.setFont("Helvetica", 10)
    for idx, line in enumerate(text_lines[:45]):
        pdf.setFillColor(colors.HexColor("#1d6f43"))
        pdf.drawString(right_x, top_y - idx * 14, line)

    pdf.save()
    return output
