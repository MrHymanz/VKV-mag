"""Preserve editorial word breaks instead of treating them as spelling errors."""
import re

HYPHENS = r"\-\u00ad\u2010\u2011"
BROKEN_WORD = re.compile(rf"\w+(?:[{HYPHENS}]\w+)*[{HYPHENS}]\s+\w+(?:[{HYPHENS}]\w+)*")


def protected_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in BROKEN_WORD.finditer(text)]


def overlaps_break(text: str, start: int, end: int) -> bool:
    return any(start < stop and end > begin or start == end and begin < start < stop
               for begin, stop in protected_spans(text))


def changes_word_break(original: str, replacement: str) -> bool:
    def normalized(value):
        return ' '.join(value.casefold().split())
    def joined(value):
        return re.sub(rf"[\s{HYPHENS}]+", '', value.casefold())
    return normalized(original) != normalized(replacement) and joined(original) == joined(replacement)


def filter_layout_suggestion(match: dict, text: str, base_offset: int = 0) -> dict | None:
    rule_id = match.get('rule', {}).get('id', '')
    if rule_id == 'NL_AFGEBROKEN_WOORD':
        return None
    start = base_offset + int(match.get('offset', 0))
    end = start + int(match.get('length', 0))
    if overlaps_break(text, start, end):
        return None
    replacements = match.get('replacements', [])
    filtered = [item for item in replacements
                if not changes_word_break(text[start:end], item.get('value', ''))]
    if replacements and not filtered:
        return None
    return {**match, 'replacements': filtered}
