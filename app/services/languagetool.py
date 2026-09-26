from __future__ import annotations

import json
import re
from typing import Any

import httpx


class LanguageToolClient:
    def __init__(self, base_url: str, timeout: float = 20.0, max_chars_per_request: int = 15000):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_chars_per_request = max_chars_per_request
        self.check_url = f"{self.base_url}/v2/check"

    def _split_text(self, text: str) -> list[str]:
        stripped = text.strip()
        if not stripped:
            return []
        if len(stripped) <= self.max_chars_per_request:
            return [stripped]

        sentences = re.split(r"(?<=[.!?])\s+", stripped)
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            candidate = sentence if not current else f"{current} {sentence}"
            if len(candidate) <= self.max_chars_per_request:
                current = candidate
                continue

            if current.strip():
                chunks.append(current.strip())
            current = sentence.strip()

        if current.strip():
            chunks.append(current.strip())

        return chunks or [stripped[: self.max_chars_per_request]]

    def _request_chunk(self, chunk: str, language: str = "nl-NL") -> list[dict[str, Any]]:
        payload = {
            "text": chunk,
            "language": language,
            "enabledRules": "doubled_words,grammar,spelling,punctuation,style",
        }

        try:
            response = httpx.post(
                self.check_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("matches", [])
        except httpx.HTTPError as exc:
            raise RuntimeError(f"LanguageTool niet bereikbaar op {self.check_url}: {exc}") from exc

    def check_text(self, text: str, language: str = "nl-NL") -> list[dict[str, Any]]:
        if not text or not text.strip():
            return []

        all_matches: list[dict[str, Any]] = []
        text_offset = 0

        for chunk in self._split_text(text):
            matches = self._request_chunk(chunk, language=language)
            for match in matches:
                mutated = dict(match)
                offset = int(mutated.get("offset", 0))
                mutated["offset"] = offset + text_offset
                context = mutated.get("context")
                if isinstance(context, dict):
                    adjusted_context = dict(context)
                    context_offset = int(adjusted_context.get("offset", 0))
                    adjusted_context["offset"] = context_offset + text_offset
                    mutated["context"] = adjusted_context
                all_matches.append(mutated)
            text_offset += len(chunk)

        return all_matches

    def check_document_chunks(self, text: str, language: str = "nl-NL") -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        total_offset = 0

        for index, chunk in enumerate(self._split_text(text), start=1):
            matches = self._request_chunk(chunk, language=language)
            normalized_matches = []
            for match in matches:
                normalized = self.normalize_issue(match)
                offset = int(match.get("offset", 0))
                normalized["offset"] = offset + total_offset
                context = match.get("context", {})
                if isinstance(context, dict):
                    adjusted_context = dict(context)
                    adjusted_context["offset"] = int(adjusted_context.get("offset", 0)) + total_offset
                    normalized["context"] = adjusted_context
                normalized_matches.append(normalized)

            chunks.append({
                "id": index,
                "text": chunk,
                "start": total_offset,
                "issues": normalized_matches,
            })
            total_offset += len(chunk)

        return chunks

    @staticmethod
    def _humanize_issue_label(value: str | None) -> str:
        label = (value or "").strip()
        if not label or label.lower() == "unknown":
            return "Controle"

        normalized = label.lower().replace("-", "_")
        keyword_map = {
            "whitespace": "Witruimte",
            "whitespace_rule": "Witruimte",
            "spelling": "Spelling",
            "morfologik": "Spelling",
            "morfologik_rule": "Spelling",
            "grammar": "Grammatica",
            "grammatica": "Grammatica",
            "style": "Stijl",
            "punctuation": "Interpunctie",
            "comma": "Interpunctie",
            "duplication": "Herhaling",
            "duplicate": "Herhaling",
            "consistency": "Consistentie",
            "ambiguity": "Interpretatie",
        }

        for key, human_label in keyword_map.items():
            if key in normalized:
                return human_label

        return label.replace("_", " ").title()

    def normalize_issue(self, match: dict[str, Any]) -> dict[str, Any]:
        replacements = []
        for replacement in match.get("replacements", [])[:5]:
            replacements.append({
                "value": replacement.get("value"),
                "short_description": replacement.get("shortDescription", ""),
            })

        category_name = match.get("category", {}).get("name", "unknown")
        rule_id = match.get("rule", {}).get("id", "unknown")
        display_category = self._humanize_issue_label(category_name if category_name and category_name.lower() != "unknown" else rule_id)
        display_rule = self._humanize_issue_label(rule_id if rule_id and rule_id.lower() != "unknown" else category_name)

        return {
            "message": match.get("message", ""),
            "short_message": match.get("shortMessage", ""),
            "category": category_name,
            "display_category": display_category,
            "rule_id": rule_id,
            "display_rule": display_rule,
            "offset": match.get("offset", 0),
            "length": match.get("length", 0),
            "replacements": replacements,
            "context": match.get("context", {}).get("text", ""),
            "context_offset": match.get("context", {}).get("offset", 0),
            "sentence": match.get("sentence", ""),
        }
