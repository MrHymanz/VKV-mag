from __future__ import annotations

import difflib
import re
from pathlib import Path

import fitz


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


def _normalize_word_tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", text or "")]


def _find_changed_words(original_text: str, revised_text: str) -> set[str]:
    original_tokens = _normalize_word_tokens(original_text)
    revised_tokens = _normalize_word_tokens(revised_text)
    matcher = difflib.SequenceMatcher(None, original_tokens, revised_tokens, autojunk=False)
    changed: set[str] = set()

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed.update(original_tokens[i1:i2])
        changed.update(revised_tokens[j1:j2])

    return changed


def _render_revised_page_text(page: fitz.Page, source_page: fitz.Page | None, revised_text: str) -> None:
    page.clean_contents()

    if source_page is not None:
        source_pix = source_page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
        page.insert_image(page.rect, stream=source_pix.tobytes("png"))

    source_text = source_page.get_text("text") if source_page is not None else ""
    changed_words = _find_changed_words(source_text, revised_text)
    paragraphs = [part.strip() for part in revised_text.splitlines() if part.strip()] or [revised_text]
    blocks = source_page.get_text("blocks") if source_page is not None else []

    if blocks and changed_words:
        for block in blocks:
            if len(block) < 6:
                continue
            x0, y0, x1, y1, block_text, _, _ = block[:7]
            normalized = _normalize_word_tokens(str(block_text or ""))
            if not normalized or not set(normalized).intersection(changed_words):
                continue

            rect = fitz.Rect(float(x0) - 3, float(y0) - 3, float(x1) + 3, float(y1) + 3)
            page.draw_rect(rect, fill=(1.0, 0.86, 0.86), color=(0.8, 0.2, 0.2), overlay=True)

    if not blocks:
        margin_left = 60
        margin_top = 70
        line_height = 14
        max_lines = 55
        lines_drawn = 0
        for paragraph in paragraphs[:max_lines]:
            for line in _wrap_text_for_render(paragraph):
                if lines_drawn >= max_lines:
                    break
                y_position = page.rect.height - margin_top - lines_drawn * line_height
                if y_position < 30:
                    break
                page.insert_text(
                    (margin_left, y_position),
                    line,
                    fontsize=11,
                    color=(0.1, 0.38, 0.25),
                    overlay=True,
                )
                lines_drawn += 1
            if lines_drawn >= max_lines:
                break
        return

    block_limit = min(len(blocks), max(1, len(paragraphs)))
    for index in range(block_limit):
        block = blocks[index]
        if len(block) < 4:
            continue
        x0, y0, x1, y1, _, _, _ = block[:7]
        box = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        if box.width <= 20 or box.height <= 10:
            continue

        paragraph = paragraphs[index % len(paragraphs)]
        page.draw_rect(box, fill=(0.85, 0.97, 0.88), color=(0.1, 0.55, 0.35), overlay=True)
        page.insert_textbox(
            box,
            paragraph,
            fontsize=9.5,
            fontname="helv",
            color=(0.1, 0.38, 0.25),
            align=1,
            overlay=True,
        )


def build_comparison_pdf_preview(
    original_pdf_path: str | Path | None,
    revised_text: str,
    output_path: str | Path,
    page_index: int = 0,
) -> Path:
    output = Path(output_path)
    if original_pdf_path and Path(original_pdf_path).exists():
        source_doc = fitz.open(str(original_pdf_path))
        target_page_index = max(0, min(page_index, len(source_doc) - 1))
        src_page = source_doc[target_page_index]
        page_rect = src_page.rect
        width = float(page_rect.width)
        height = float(page_rect.height)

        compare_doc = fitz.open()
        compare_page = compare_doc.new_page(width=width * 2 + 40, height=height)

        pix = src_page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
        compare_page.insert_image(fitz.Rect(0, 0, width, height), stream=pix.tobytes("png"))

        revised_page = fitz.open()
        revised_page.new_page(width=width, height=height)
        _render_revised_page_text(revised_page[0], src_page, revised_text)
        revised_pix = revised_page[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
        compare_page.insert_image(fitz.Rect(width + 20, 0, width * 2 + 20, height), stream=revised_pix.tobytes("png"))

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
