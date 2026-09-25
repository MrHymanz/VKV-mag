from dataclasses import dataclass


@dataclass
class CorrectionDecision:
    issue_id: str
    accepted: bool
    replacement: str | None = None
    ignored: bool = False
    category: str = "spelling"
