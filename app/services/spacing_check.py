"""Explicit, reviewable spacing suggestions for editable DOCX text."""
import re


def add_docx_spacing_issues(text: str, chunks: list[dict]) -> list[dict]:
    # Only ordinary spaces between non-whitespace characters, not indentation,
    # tabs, line breaks or non-breaking spaces used for layout.
    spaces = list(re.finditer(r'(?<=\S) {2,}(?=\S)', text))
    for match in spaces:
        index = next((i for i, chunk in enumerate(chunks)
                      if chunk['start'] <= match.start() < chunk['start'] + len(chunk['text'])), None)
        if index is None:
            continue
        chunk = chunks[index]
        # LanguageTool may split inside a space run. Keep the entire editable
        # range in one review chunk so applying it cannot lose characters.
        while match.end() > chunk['start'] + len(chunk['text']) and index + 1 < len(chunks):
            following = chunks.pop(index + 1)
            chunk['text'] += following['text']
            chunk['issues'].extend(following['issues'])
        begin = max(text.rfind('\n', 0, match.start()) + 1, match.start() - 45)
        end = text.find('\n', match.end())
        end = min(len(text) if end == -1 else end, match.end() + 45)
        context = text[begin:end]
        # Suppress duplicate LanguageTool whitespace suggestions, not other
        # grammar/spelling suggestions near the same words.
        def duplicate(issue):
            start = issue['offset']
            stop = start + issue['length']
            return (start < match.end() and stop > match.start()
                    and bool(text[start:stop]) and not text[start:stop].strip()
                    and all(not item.get('value', '').strip() for item in issue.get('replacements', [])))
        chunk['issues'] = [issue for issue in chunk['issues'] if not duplicate(issue)]
        chunk['issues'].append({
            'rule_id': 'VKV_DOUBLE_SPACES', 'kind': 'grammar',
            'display_category': 'Witruimte', 'category': 'Witruimte',
            'display_rule': 'Dubbele spaties', 'short_message': 'Dubbele spaties',
            'message': f'{len(match.group())} spaties tussen woorden. Vervang door één spatie. Context: “{context}”',
            'offset': match.start(), 'length': len(match.group()),
            'replacements': [{'value': ' ', 'short_description': 'Eén spatie'}],
            'accepted': False, 'requires_confirmation': True,
            'context': context, 'context_offset': match.start() - begin,
        })
    for index, chunk in enumerate(chunks, start=1):
        chunk['id'] = index
        chunk['issues'].sort(key=lambda issue: issue['offset'])
    return chunks
