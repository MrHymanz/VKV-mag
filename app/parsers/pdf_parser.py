from pathlib import Path

from pypdf import PdfReader

from app.models.document import ParsedDocument
from app.parsers.base import BaseParser


class PdfParser(BaseParser):
    supported_extensions = {".pdf"}

    def parse(self, file_path: Path) -> ParsedDocument:
        reader = PdfReader(str(file_path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)

        text = "\n".join(page for page in pages if page)
        return ParsedDocument(
            file_path=file_path,
            file_name=file_path.name,
            file_type="pdf",
            text=text,
            metadata={"page_count": len(reader.pages)},
            original_extension=file_path.suffix.lower(),
        )
