from __future__ import annotations

import difflib
import re
from pathlib import Path

import fitz

from app.parsers.pdf_parser import page_text
from app.services.layout_protection import changes_word_break, overlaps_break
from app.services.pdf_text_style import PageTypography


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


def _comparison_pages(source_doc: fitz.Document, page_index: int, revised_text: str, warnings: list[str] | None = None) -> tuple[fitz.Document, fitz.Document]:
    original = fitz.open()
    original.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
    revised = fitz.open()
    revised.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
    left, right = original[0], revised[0]
    notes = apply_pdf_page_corrections(right, revised_text, original_page=left, highlight=True)
    if warnings is not None:
        warnings.extend(notes)
    return original, revised


def apply_pdf_page_corrections(
    right: fitz.Page, revised_text: str,
    original_page: fitz.Page | None = None, highlight: bool = False,
) -> list[str]:
    """Use the same corrections for the comparison and the clean download."""
    typography = PageTypography(right)
    words = typography.words
    # Preserve punctuation and capitalisation: those may themselves be corrections.
    tokens = re.findall(r"\S+", revised_text)
    matcher = difflib.SequenceMatcher(None, [word[4] for word in words], tokens, autojunk=False)
    source_text = " ".join(word[4] for word in words)
    offsets = []
    cursor = 0
    for word in words:
        offsets.append(cursor)
        cursor += len(word[4]) + 1
    changes = {}
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
        added = tokens[j1:j2]
        if not words:
            continue
        if removed:
            for index in range(i1, i2):
                changes[index] = ""
            # Keep each source line separate for corrections spanning line breaks.
            groups = []
            for index in range(i1, i2):
                if not groups or words[groups[-1][-1]][5:7] != words[index][5:7]:
                    groups.append([])
                groups[-1].append(index)
            cursor = 0
            for index, group in enumerate(groups):
                count = len(added) - cursor if index == len(groups) - 1 else min(len(group), len(added) - cursor)
                if count <= 0:
                    break
                group_tokens = added[cursor:cursor + count]
                for word_index, source_index in enumerate(group):
                    if word_index >= len(group_tokens):
                        break
                    replacement = (" ".join(group_tokens[word_index:]) if word_index == len(group) - 1
                                   else group_tokens[word_index])
                    changes[source_index] = replacement
                cursor += count
        elif added:
            if i1 == len(words) or (i1 > 0 and words[i1 - 1][5:7] == words[i1][5:7]):
                anchor = i1 - 1
                changes[anchor] = changes.get(anchor, words[anchor][4]) + " " + " ".join(added)
            else:
                changes[i1] = " ".join(added) + " " + changes.get(i1, words[i1][4])

    lines = {}
    for index, word in enumerate(words):
        lines.setdefault(tuple(word[5:7]), []).append(index)
    redactions, replacements, highlights = [], [], []
    for line_key, indices in lines.items():
        if not any(index in changes for index in indices):
            continue
        previous_end = None
        previous_word = None
        for index in indices:
            word = words[index]
            text = changes.get(index, word[4])
            gap = max(0, word[0] - previous_word[2]) if previous_word is not None else 0
            x = max(word[0], previous_end + gap) if previous_end is not None else word[0]
            previous_word = word
            if index not in changes and abs(x - word[0]) < 0.02:
                previous_end = word[2]
                continue
            glyphs = typography.glyphs(word)
            redactions.append((word, index in changes))
            if not text:
                continue
            planned, end_x = typography.plan(glyphs, text, fitz.Point(x, glyphs[0].origin.y))
            replacements.extend(planned)
            if index in changes:
                highlights.append(fitz.Rect(x, word[1], end_x, word[3]))
            previous_end = end_x
        last = words[indices[-1]]
        # If a correction grows, move the following words only as far as needed
        # to retain the original spaces. Never resize letters or enter a column.
        boundary = min((other[0] for other in words
                        if tuple(other[5:7]) != line_key and other[0] >= last[2] - 0.01
                        and other[1] < last[3] and other[3] > last[1]), default=right.rect.width)
        if previous_end is not None and previous_end > boundary + 0.1:
            changed = " ".join(changes[index] for index in indices if index in changes)
            raise ValueError(f'De correctie “{changed}” past niet op pagina {right.number + 1} met de oorspronkelijke lettergrootte. Vink deze correctie uit of pas de opmaak in het bronbestand aan.')
    # All fonts and available space are checked before removing any text.
    for word, changed in redactions:
        rect = fitz.Rect(word[:4])
        if original_page is not None and changed:
            _highlight(original_page, rect, (1, 0.2, 0.2))
        strip = fitz.Rect(rect.x0 + 0.1, rect.y0 + rect.height * 0.45,
                          rect.x1 - 0.1, rect.y0 + rect.height * 0.55)
        right.add_redact_annot(strip, fill=False, cross_out=False)
    if redactions:
        right.apply_redactions(images=0, graphics=0)
    if highlight:
        for rect in highlights:
            _highlight(right, rect, (0.15, 0.85, 0.3))
    typography.render(replacements)
    return (["Een nieuw leesteken ontbrak in het ingesloten lettertype. Alleen dat teken gebruikt een passend vervangend font; kleur en grootte zijn behouden."]
            if typography.punctuation_fallbacks else [])


def build_comparison_pdf_preview(
    original_pdf_path: str | Path | None,
    revised_text: str,
    output_path: str | Path,
    page_index: int = 0,
    original_text: str | None = None,
    warnings: list[str] | None = None,
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

        original, revised = _comparison_pages(source_doc, target_page_index, revised_text, warnings)
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
