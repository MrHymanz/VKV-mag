from abc import ABC, abstractmethod
from pathlib import Path

from app.models.document import ParsedDocument


class BaseParser(ABC):
    @property
    @abstractmethod
    def supported_extensions(self):
        raise NotImplementedError

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument:
        raise NotImplementedError
