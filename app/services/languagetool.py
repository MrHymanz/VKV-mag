from __future__ import annotations

from typing import Any

import httpx

from app.services.layout_protection import filter_layout_suggestion


class LanguageToolClient:
    def __init__(self, base_url: str, timeout: float = 20.0, max_chars_per_request: int = 15000, sensitivity: str = "cautious"):
        if sensitivity not in {"cautious", "normal", "strict"}:
            raise ValueError("Onbekende gevoeligheid")
        self.sensitivity = sensitivity
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_chars_per_request = max_chars_per_request
        self.check_url = f"{self.base_url}/v2/check"

    @staticmethod
    def issue_kind(match: dict[str, Any]) -> str:
        rule = match.get("rule", {})
        rule_id = rule.get("id", "")
        category = rule.get("category", {}).get("id", "")
        issue_type = rule.get("issueType", "")
        # LanguageTool labels these word-choice guesses as misspellings too.
        # Check them first: "de mijne" is valid despite NL_SIMPLE_REPLACE_MIJNE.
        if category in {"VERGISSINGEN", "CONFUSED_WORDS", "STYLE", "REDUNDANCY"} or rule_id.startswith("NL_SIMPLE_REPLACE"):
            return "suggestion"
        if issue_type in {"style", "register", "locale", "non-conformance"}:
            return "suggestion"
        if category in {"PUNCTUATION", "TYPOGRAPHY", "GRAMMAR", "GRAMMATICA", "CASING", "WHITESPACE"} or issue_type in {"grammar", "typographical", "whitespace"}:
            return "grammar"
        if issue_type == "misspelling" or category == "TYPOS":
            return "spelling"
        # Unknown categories should never become automatic corrections.
        return "suggestion"

    def includes_issue(self, match: dict[str, Any]) -> bool:
        kind = self.issue_kind(match)
        return (self.sensitivity == "strict" or kind == "spelling"
                or (self.sensitivity == "normal" and kind == "grammar"))

    def _split_text(self, text: str) -> list[str]:
        if not text.strip():
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chars_per_request, len(text))
            if end < len(text):
                # Keep whitespace verbatim so LanguageTool offsets still map to
                # the original page, including text split across requests.
                boundary = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
                if boundary > start:
                    end = boundary + 1
            chunks.append(text[start:end])
            start = end
        return chunks

    def _request_chunk(self, chunk: str, language: str = "nl-NL") -> list[dict[str, Any]]:
        payload = {
            "text": chunk,
            "language": language,
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
            matches = (filter_layout_suggestion(match, chunk) for match in data.get("matches", []))
            return [match for match in matches if match is not None and self.includes_issue(match)]
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
                match = filter_layout_suggestion(match, text, text_offset)
                if match is None:
                    continue
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
                match = filter_layout_suggestion(match, text, total_offset)
                if match is None:
                    continue
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

        kind = self.issue_kind(match)
        category_name = match.get("rule", {}).get("category", {}).get("name", "unknown")
        rule_id = match.get("rule", {}).get("id", "unknown")
        display_category = self._humanize_issue_label(category_name if category_name and category_name.lower() != "unknown" else rule_id)
        display_rule = self._humanize_issue_label(rule_id if rule_id and rule_id.lower() != "unknown" else category_name)

        return {
            "kind": kind,
            "requires_confirmation": kind != "spelling",
            "accepted": kind == "spelling",
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
