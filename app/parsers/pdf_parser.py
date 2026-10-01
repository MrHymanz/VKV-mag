from pathlib import Path

import fitz

from app.models.document import ParsedDocument
from app.parsers.base import BaseParser


def page_text(page: fitz.Page) -> str:
    """Use the same word order for checking and positioning PDF corrections."""
    return " ".join(word[4] for word in page.get_text("words"))


class PdfParser(BaseParser):
    supported_extensions = {".pdf"}

    def parse(self, file_path: Path) -> ParsedDocument:
        with fitz.open(file_path) as document:
            pages = [page_text(page) for page in document]
        return ParsedDocument(
            file_path=file_path,
            file_name=file_path.name,
            file_type="pdf",
            text="\n".join(pages),
            metadata={"page_count": len(pages), "pages": pages},
            original_extension=file_path.suffix.lower(),
        )
