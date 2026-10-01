import fitz
import pytest

from app.services.layout_protection import changes_word_break, filter_layout_suggestion
from app.services.languagetool import LanguageToolClient
from app.services.pdf_preview import build_comparison_pdf_preview


def suggestion(offset, length, replacement, rule='MORFOLOGIK_RULE_NL_NL'):
    return {'offset': offset, 'length': length, 'replacements': [{'value': replacement}],
            'rule': {'id': rule, 'issueType': 'misspelling', 'category': {'id': 'TYPOS'}}}


@pytest.mark.parametrize('mode', ['cautious', 'normal', 'strict'])
def test_split_word_rules_and_fragments_are_excluded_in_every_mode(monkeypatch, mode):
    text = 'Betrouwba- re auto techniek met spelfoutt.'
    matches = [suggestion(0, 13, 'Betrouwbare', 'NL_AFGEBROKEN_WOORD'),
               suggestion(0, 10, 'Betrouwbaar'), suggestion(11, 2, 'er'),
               suggestion(14, 13, 'autotechniek'), suggestion(text.index('spelfoutt'), 9, 'spelfout')]
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'matches': matches}
    monkeypatch.setattr('app.services.languagetool.httpx.post', lambda *a, **kw: Response())
    issues = LanguageToolClient('http://unused', sensitivity=mode).check_document_chunks(text)[0]['issues']
    assert len(issues) == 1
    assert issues[0]['offset'] == text.index('spelfoutt')


@pytest.mark.parametrize('before,after,expected', [
    ('auto techniek', 'autotechniek', True), ('autotechniek', 'auto techniek', True),
    ('Amazon techniek', 'Amazon-techniek', True), ('Vol- vo', 'Volvo', True),
    ('bijzon\u00ad dere', 'bijzondere', True), ('auto  techniek', 'auto techniek', False),
    ('beginners maar', 'beginners, maar', False), ('mijne', 'mijn', False),
])
def test_detects_word_break_changes_only(before, after, expected):
    assert changes_word_break(before, after) is expected


def test_split_word_protection_across_language_tool_requests(monkeypatch):
    client = LanguageToolClient('http://unused', max_chars_per_request=11)
    text = 'Betrouwba- re auto'
    monkeypatch.setattr(client, '_request_chunk', lambda chunk, language:
                        [suggestion(0, 2, 'er')] if chunk.startswith('re') else [])
    assert not any(chunk['issues'] for chunk in client.check_document_chunks(text))


def test_unsafe_alternatives_removed_but_spelling_suggestion_kept():
    match = suggestion(0, 8, 'auto bus')
    match['replacements'].append({'value': 'autobus'})
    # A spelling error remains fixable; a pure word split does not.
    match['replacements'][0]['value'] = 'auto buss'
    filtered = filter_layout_suggestion(match, 'autobuss')
    assert filtered['replacements'] == [{'value': 'autobus'}]


def test_pdf_keeps_editorial_line_break_when_old_request_joins_it(tmp_path):
    source = tmp_path / 'split.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=160)
        page.insert_text((40, 50), 'Betrouwba-', fontsize=12)
        page.insert_text((40, 70), 're auto met spelfoutt.', fontsize=12)
        doc.save(source)
    output = tmp_path / 'compare.pdf'
    build_comparison_pdf_preview(source, 'Betrouwbare auto met spelfout.', output,
                                 original_text='Betrouwba- re auto met spelfoutt.')
    with fitz.open(output) as doc:
        page = doc[0]
        right = page.get_text(clip=fitz.Rect(420, 0, 820, 160))
        assert 'Betrouwba-' in right
        assert 're auto met' in right
        assert 'spelfoutt' not in right
        assert 'spelfout' in right
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    if 'Betrouwba-' in span['text']:
                        assert span['size'] == 12
