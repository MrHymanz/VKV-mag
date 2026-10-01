import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.languagetool import LanguageToolClient


def match(rule_id, category, issue_type):
    return {
        'rule': {'id': rule_id, 'category': {'id': category, 'name': category}, 'issueType': issue_type},
        'message': 'Testvoorstel', 'offset': 3, 'length': 5,
        'replacements': [{'value': 'mijn'}],
    }


MATCHES = [
    match('MORFOLOGIK_RULE_NL_NL', 'TYPOS', 'misspelling'),
    match('NL_SIMPLE_REPLACE_MIJNE', 'VERGISSINGEN', 'misspelling'),
    match('GRAMMAR_RULE', 'GRAMMAR', 'grammar'),
    match('DUBBELE_SPATIE', 'PUNCTUATION', 'uncategorized'),
    match('STYLE_RULE', 'STYLE', 'style'),
    match('UNKNOWN', 'OTHER', 'uncategorized'),
]


@pytest.mark.parametrize('level,expected', [
    ('cautious', [0]), ('normal', [0, 2, 3]), ('strict', list(range(6))),
])
def test_sensitivity_filters_actual_response(monkeypatch, level, expected):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'matches': MATCHES}
    monkeypatch.setattr('app.services.languagetool.httpx.post', lambda *a, **kw: Response())
    client = LanguageToolClient('http://unused', sensitivity=level)
    issues = client.check_document_chunks('De mijne is betrouwbaar.')[0]['issues']
    assert [issue['rule_id'] for issue in issues] == [MATCHES[i]['rule']['id'] for i in expected]
    for issue in issues:
        is_spelling = issue['rule_id'] == 'MORFOLOGIK_RULE_NL_NL'
        assert issue['accepted'] is is_spelling
        assert issue['requires_confirmation'] is not is_spelling


def test_mijne_is_never_automatically_accepted():
    client = LanguageToolClient('http://unused', sensitivity='strict')
    issue = client.normalize_issue(MATCHES[1])
    assert issue['category'] == 'VERGISSINGEN'
    assert issue['accepted'] is False
    assert issue['requires_confirmation'] is True


@pytest.mark.parametrize('level', [None, 'normal', 'strict'])
def test_upload_passes_sensitivity_to_checker(monkeypatch, tmp_path, level):
    from app import main
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    observed = []
    def check(self, text, language):
        observed.append(self.sensitivity)
        return []
    monkeypatch.setattr(LanguageToolClient, '_request_chunk', check)
    response = TestClient(app).post('/upload', files={'file': ('test.txt', b'De mijne is goed.')},
                                    data={} if level is None else {'sensitivity': level})
    assert response.status_code == 200
    assert observed == [level or 'cautious']
    assert response.json()['sensitivity'] == (level or 'cautious')


def test_invalid_sensitivity_rejected_before_upload(monkeypatch, tmp_path):
    from app import main
    monkeypatch.setattr(main, 'UPLOAD_DIR', tmp_path)
    response = TestClient(app).post('/upload', files={'file': ('test.txt', b'test')},
                                    data={'sensitivity': 'anything'})
    assert response.status_code == 422
    assert not list(tmp_path.iterdir())
