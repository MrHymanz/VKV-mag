"""Read and reuse the typography of the actual PDF glyphs being corrected."""
from __future__ import annotations

import difflib
import re
import statistics
import unicodedata
from dataclasses import dataclass

import fitz


def _font_name(name: str) -> str:
    return re.sub(r"^[A-Z]{6}\+", "", name).removesuffix("-Identity-H")


def _font_key(name: str) -> str:
    # PDF resource names and PostScript names can differ only in spacing or '-'.
    return re.sub(r"[^a-z0-9]", "", _font_name(name).lower())


@dataclass
class Face:
    font: fitz.Font
    resource: str
    data: bytes | None = None


@dataclass
class Glyph:
    text: str
    origin: fitz.Point
    rect: fitz.Rect
    span: dict
    direction: tuple


@dataclass
class DrawGlyph:
    text: str
    origin: fitz.Point
    face: Face
    size: float
    scale_x: float
    scale_y: float
    color: tuple
    opacity: float
    render_mode: int


class PageTypography:
    def __init__(self, page: fitz.Page):
        self.page = page
        self.words = page.get_text("words")
        self.faces: dict[int, Face] = {}
        self.fonts = page.get_fonts(full=True)
        self.word_glyphs = {}
        self.metrics = {}
        self.punctuation_fallbacks: set[str] = set()
        # Match the words extractor's block numbers: images must not increment
        # the raw-text block index on illustrated magazine pages.
        flags = fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES
        for block in page.get_text("rawdict", flags=flags)["blocks"]:
            for line_index, line in enumerate(block.get("lines", [])):
                glyphs = [Glyph(char["c"], fitz.Point(char["origin"]), fitz.Rect(char["bbox"]),
                                span, line["dir"])
                          for span in line["spans"] for char in span["chars"]]
                text = "".join(glyph.text for glyph in glyphs)
                # A glyph may represent a ligature; do not assume one Unicode
                # character equals one glyph in the underlying font.
                for word_index, match in enumerate(re.finditer(r"\S+", text)):
                    cursor = 0
                    selected = []
                    for glyph in glyphs:
                        end = cursor + len(glyph.text)
                        if cursor < match.end() and end > match.start():
                            selected.append(glyph)
                        cursor = end
                    self.word_glyphs[(block["number"], line_index, word_index)] = selected

    def glyphs(self, word) -> list[Glyph]:
        glyphs = self.word_glyphs.get(tuple(word[5:8]), [])
        if not glyphs or "".join(g.text for g in glyphs) != word[4]:
            raise ValueError(f'De opmaak van “{word[4]}” kan niet betrouwbaar worden gelezen. Vink deze correctie uit.')
        if any(abs(g.direction[0] - 1) > 0.001 or abs(g.direction[1]) > 0.001 for g in glyphs):
            raise ValueError(f'De gedraaide tekst “{word[4]}” kan niet met behoud van opmaak worden aangepast. Vink deze correctie uit.')
        return glyphs

    def _face(self, entry) -> Face:
        xref = entry[0]
        if xref not in self.faces:
            _, _, _, data = self.page.parent.extract_font(xref)
            if data:
                face = Face(fitz.Font(fontbuffer=data), f"VKVfont{xref}", data)
            else:
                name = _font_name(entry[3])
                try:
                    face = Face(fitz.Font(fontname=name), name)
                except Exception as exc:
                    raise ValueError(f'Het oorspronkelijke lettertype {name} ontbreekt in de PDF. De correctie kan niet met behoud van opmaak worden gemaakt.') from exc
            self.faces[xref] = face
        return self.faces[xref]

    def original_face(self, glyph: Glyph) -> Face:
        name = glyph.span["font"]
        entries = [entry for entry in self.fonts if _font_key(entry[3]) == _font_key(name)]
        for entry in entries:
            face = self._face(entry)
            if all(face.font.has_glyph(ord(char)) for char in glyph.text):
                return face
        raise ValueError(f'Het oorspronkelijke lettertype {name} kan niet worden hergebruikt. Vink deze correctie uit.')

    def face_for(self, glyph: Glyph, text: str) -> Face:
        face = self.original_face(glyph)
        if all(face.font.has_glyph(ord(char)) for char in text):
            return face
        # Another subset of the same family may contain the new character.
        name = _font_name(glyph.span["font"])
        for page in self.page.parent:
            for entry in page.get_fonts(full=True):
                if _font_key(entry[3]) == _font_key(name):
                    candidate = self._face(entry)
                    if all(candidate.font.has_glyph(ord(char)) for char in text):
                        return candidate
        # A subset can omit a newly added comma. Substitute only that punctuation,
        # never the word's letters, and keep the source color, size and baseline.
        if all(unicodedata.category(char).startswith("P") for char in text):
            lower = name.lower()
            serif = any(part in lower for part in ("times", "serif", "georgia"))
            bold = any(part in lower for part in ("bold", "heavy", "black", "semibold"))
            italic = any(part in lower for part in ("italic", "oblique"))
            aliases = ("tiro", "tibo", "tiit", "tibi") if serif else ("helv", "hebo", "heit", "hebi")
            alias = aliases[int(bold) + 2 * int(italic)]
            fallback = Face(fitz.Font(alias), alias)
            if all(fallback.font.has_glyph(ord(char)) for char in text):
                self.punctuation_fallbacks.add(text)
                return fallback
        raise ValueError(f'Het teken “{text}” ontbreekt in het oorspronkelijke lettertype {name}. Vink deze correctie uit om de opmaak te behouden.')

    def measurements(self, glyph: Glyph) -> tuple[float, float, float]:
        key = id(glyph.span)
        if key not in self.metrics:
            face = self.original_face(glyph)
            span = glyph.span
            heights, widths, tracking = [], [], []
            for char in span["chars"]:
                unit_width = face.font.text_length(char["c"], fontsize=1)
                box = fitz.Rect(char["bbox"])
                if unit_width > 0 and not char["c"].isspace():
                    widths.append(box.width / unit_width)
                    heights.append(box.height / (span["ascender"] - span["descender"]))
            for first, second in zip(span["chars"], span["chars"][1:]):
                if not first["c"].isspace() and not second["c"].isspace():
                    tracking.append(second["origin"][0] - first["bbox"][2])
            self.metrics[key] = (statistics.median(widths) if widths else span["size"],
                                 statistics.median(heights) if heights else span["size"],
                                 statistics.median(tracking) if tracking else 0)
        return self.metrics[key]

    def plan(self, glyphs: list[Glyph], text: str, origin: fitz.Point | None = None) -> tuple[list[DrawGlyph], float]:
        old = "".join(g.text for g in glyphs)
        source_indices = []
        for index, glyph in enumerate(glyphs):
            source_indices.extend([index] * len(glyph.text))
        styles = {}
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, text, autojunk=False).get_opcodes():
            for offset, index in enumerate(range(j1, j2)):
                reference = min(i1 + offset, i2 - 1) if i2 > i1 else max(0, i1 - 1)
                styles[index] = glyphs[source_indices[reference]]
        origin = origin or glyphs[0].origin
        x = origin.x
        planned = []
        last_tracking = 0
        for index, char in enumerate(text):
            source = styles[index]
            face = self.face_for(source, char)
            horizontal, vertical, tracking = self.measurements(source)
            size = source.span["size"]
            color = fitz.sRGB_to_pdf(source.span["color"])
            flags = source.span.get("char_flags", 16)
            mode = 2 if flags & 16 and flags & 32 else (1 if flags & 32 else 0)
            planned.append(DrawGlyph(char, fitz.Point(x, origin.y + source.origin.y - glyphs[0].origin.y),
                                     face, size, horizontal / size, vertical / size, color,
                                     source.span.get("alpha", 255) / 255, mode))
            x += face.font.text_length(char, fontsize=horizontal) + tracking
            last_tracking = tracking
        return planned, x - last_tracking

    def render(self, glyphs: list[DrawGlyph]) -> None:
        installed = set()
        for glyph in glyphs:
            face = glyph.face
            if face.resource not in installed:
                self.page.insert_font(fontname=face.resource, fontbuffer=face.data)
                installed.add(face.resource)
            self.page.insert_text(glyph.origin, glyph.text, fontsize=glyph.size,
                                  fontname=face.resource, color=glyph.color,
                                  fill=glyph.color, render_mode=glyph.render_mode,
                                  fill_opacity=glyph.opacity, stroke_opacity=glyph.opacity,
                                  morph=(glyph.origin, fitz.Matrix(glyph.scale_x, glyph.scale_y)))
