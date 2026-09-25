from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ParsedDocument:
    file_path: Path
    file_name: str
    file_type: str
    text: str
    metadata: dict = field(default_factory=dict)
    issues: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    original_extension: Optional[str] = None


@dataclass
class Correction:
    start: int
    end: int
    original: str
    replacement: str
    category: str = "spelling"
    message: str = ""
    rule_id: Optional[str] = None
