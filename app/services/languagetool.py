from __future__ import annotations

import json
from typing import Any

import httpx


class LanguageToolClient:
    def __init__(self, base_url: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.check_url = f"{self.base_url}/v2/check"

    def check_text(self, text: str, language: str = "nl-NL") -> list[dict[str, Any]]:
        payload = {
            "text": text,
            "language": language,
            "enabledRules": [
                "doubled_words",
                "grammar",
                "spelling",
                "punctuation",
                "style",
            ],
        }

        try:
            response = httpx.post(self.check_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("matches", [])
        except httpx.HTTPError as exc:
            raise RuntimeError(f"LanguageTool niet bereikbaar op {self.check_url}: {exc}") from exc

    def normalize_issue(self, match: dict[str, Any]) -> dict[str, Any]:
        replacements = []
        for replacement in match.get("replacements", [])[:5]:
            replacements.append({
                "value": replacement.get("value"),
                "short_description": replacement.get("shortDescription", ""),
            })

        return {
            "message": match.get("message", ""),
            "short_message": match.get("shortMessage", ""),
            "category": match.get("category", {}).get("name", "unknown"),
            "rule_id": match.get("rule", {}).get("id", "unknown"),
            "offset": match.get("offset", 0),
            "length": match.get("length", 0),
            "replacements": replacements,
            "context": match.get("context", {}).get("text", ""),
            "context_offset": match.get("context", {}).get("offset", 0),
            "sentence": match.get("sentence", ""),
        }
