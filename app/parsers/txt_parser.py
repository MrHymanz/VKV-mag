from pathlib import Path

from app.models.document import ParsedDocument
from app.parsers.base import BaseParser


class TxtParser(BaseParser):
    supported_extensions = {".txt"}

    def parse(self, file_path: Path) -> ParsedDocument:
        text = file_path.read_text(encoding="utf-8")
        return ParsedDocument(
            file_path=file_path,
            file_name=file_path.name,
            file_type="txt",
            text=text,
            metadata={"lines": len(text.splitlines())},
            original_extension=file_path.suffix.lower(),
        )
