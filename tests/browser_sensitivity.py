"""Run with .venv/bin/python tests/browser_sensitivity.py after installing Chromium."""
import copy
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import fitz
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
TEXT = 'De mijne is zeker betrouwbaar. Een spelfoutt.'
DOUBTFUL = {
    'rule_id': 'NL_SIMPLE_REPLACE_MIJNE', 'message': 'Misschien bedoelt u mijn.',
    'offset': TEXT.index('mijne'), 'length': 5,
    'replacements': [{'value': 'mijn'}, {'value': 'mijne'}],
    'requires_confirmation': True, 'accepted': False,
}
SPELLING = {
    'rule_id': 'MORFOLOGIK_RULE_NL_NL', 'message': 'Mogelijke spelfout.',
    'offset': TEXT.index('spelfoutt'), 'length': 9,
    'replacements': [{'value': 'spelfout'}],
    'requires_confirmation': False, 'accepted': True,
}


def run():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1',
                               '--directory', str(ROOT / 'app')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}'
        for _ in range(50):
            try:
                if httpx.get(url).status_code == 200: break
            except httpx.ConnectError:
                time.sleep(0.1)
        with sync_playwright() as playwright:
            browser_env = os.environ.copy()
            local_libs = ROOT / '.venv/browser-libs/usr/lib/x86_64-linux-gnu'
            if local_libs.exists():
                browser_env['LD_LIBRARY_PATH'] = str(local_libs) + ':' + browser_env.get('LD_LIBRARY_PATH', '')
            font_config = ROOT / '.venv/browser-libs/fonts.conf'
            if font_config.exists():
                browser_env['FONTCONFIG_FILE'] = str(font_config)
            browser = playwright.chromium.launch(env=browser_env)
            page = browser.new_page(viewport={'width': 1280, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            mode = ['cautious']
            comparisons = []
            exports = []

            def upload(route):
                requested_mode = 'cautious' if mode[0] == 'bulk' else mode[0]
                assert f'\r\n{requested_mode}\r\n' in route.request.post_data
                if mode[0] == 'bulk':
                    first = copy.deepcopy(SPELLING)
                    second = copy.deepcopy(SPELLING)
                    second['offset'] += len(TEXT) + 1
                    route.fulfill(json={
                        'file_name': 'sample.pdf', 'stored_name': 'sample.pdf',
                        'text': f'{TEXT}\n{TEXT}', 'sensitivity': requested_mode,
                        'issues': [first, second],
                        'chunks': [
                            {'id': 1, 'page_index': 0, 'text': TEXT, 'start': 0,
                             'issues': [first], 'approved': False},
                            {'id': 2, 'page_index': 1, 'text': TEXT, 'start': len(TEXT) + 1,
                             'issues': [second], 'approved': False},
                        ],
                    })
                    return
                issues = copy.deepcopy([SPELLING] if mode[0] == 'cautious' else [DOUBTFUL, SPELLING])
                route.fulfill(json={
                    'file_name': 'sample.pdf', 'stored_name': 'sample.pdf', 'text': TEXT,
                    'sensitivity': mode[0], 'issues': issues,
                    'chunks': [{'id': 1, 'page_index': 0, 'text': TEXT, 'start': 0, 'issues': issues, 'approved': False}],
                })

            def comparison(route):
                comparisons.append(route.request.post_data_json)
                with fitz.open() as doc:
                    doc.new_page()
                    route.fulfill(content_type='application/pdf', body=doc.tobytes())

            def export(route):
                assert route.request.method == 'POST'
                exports.append(route.request.post_data_json)
                with fitz.open() as doc:
                    doc.new_page()
                    route.fulfill(content_type='application/pdf', body=doc.tobytes())

            page.route('**/upload', upload)
            page.route('**/approve-chunk', lambda route: route.fulfill(json={'approved': True}))
            page.route('**/comparison-pdf', comparison)
            page.route('**/download/sample.pdf', export)
            page.goto(url + '/templates/index.html')
            expect(page.locator('#sensitivity')).to_have_value('cautious')
            page.locator('#file-input').set_input_files({'name': 'sample.pdf', 'mimeType': 'application/pdf', 'buffer': b'test'})
            page.get_by_role('button', name='Document controleren', exact=True).click()
            expect(page.locator('.chunk-issue-item')).to_have_count(1)
            page.get_by_role('button', name='PDF vergelijken', exact=True).click()
            expect(page.locator('#pdf-preview-panel')).to_be_visible()
            assert 'De mijne' in comparisons[-1]['revised_text']
            assert 'spelfoutt' not in comparisons[-1]['revised_text']

            page.locator('#review-settings-btn').click()
            mode[0] = 'strict'
            page.locator('#sensitivity').select_option('strict')
            page.reload()
            expect(page.locator('#sensitivity')).to_have_value('strict')
            page.locator('#file-input').set_input_files({'name': 'sample.pdf', 'mimeType': 'application/pdf', 'buffer': b'test'})
            page.get_by_role('button', name='Document controleren', exact=True).click()
            expect(page.locator('.chunk-issue-item')).to_have_count(2)
            choice = page.locator('.chunk-issue-item').first.locator('input[type=checkbox]')
            expect(choice).not_to_be_checked()
            expect(page.locator('.compare-column.revised')).to_contain_text('De mijne')
            # Approving a page must not accept its doubtful suggestions in bulk.
            page.get_by_role('button', name='Deel goedkeuren', exact=True).click()
            expect(choice).not_to_be_checked()
            page.get_by_role('button', name='PDF vergelijken', exact=True).click()
            expect(page.locator('#pdf-preview-panel')).to_be_visible()
            assert 'De mijne' in comparisons[-1]['revised_text']

            choice.check()
            expect(page.locator('#pdf-preview-panel')).to_be_hidden()
            expect(page.locator('.compare-column.revised')).to_contain_text('De mijn is')
            page.get_by_role('button', name='PDF vergelijken', exact=True).click()
            expect(page.locator('#pdf-preview-panel')).to_be_visible()
            assert 'De mijn is' in comparisons[-1]['revised_text']

            page.locator('.chunk-issue-item').first.locator('select').select_option('1')
            expect(page.locator('.compare-column.revised')).to_contain_text('De mijne')
            choice.uncheck()
            page.locator('.chunk-issue-item').nth(1).locator('input').uncheck()
            page.get_by_role('button', name='PDF vergelijken', exact=True).click()
            expect(page.locator('#pdf-preview-panel')).to_be_visible()
            assert comparisons[-1]['revised_text'] == TEXT
            with page.expect_download(predicate=lambda download: download.suggested_filename == 'sample-gecorrigeerd.pdf') as download_info:
                page.locator('#download-btn').click()
            assert download_info.value.suggested_filename == 'sample-gecorrigeerd.pdf'
            assert exports[-1]['chunks'][0]['revised_text'] == TEXT

            # The local action affects one occurrence. The document-wide action
            # matches the rule, original text and selected replacement.
            page.locator('#review-settings-btn').click()
            mode[0] = 'bulk'
            page.locator('#sensitivity').select_option('cautious')
            page.locator('#file-input').set_input_files({
                'name': 'sample.pdf', 'mimeType': 'application/pdf', 'buffer': b'test',
            })
            page.get_by_role('button', name='Document controleren', exact=True).click()
            expect(page.locator('.chunk-summary')).to_contain_text('van 2')
            first_choice = page.locator('.chunk-issue-item input[type=checkbox]')
            expect(first_choice).to_be_checked()
            page.get_by_role('button', name='Nergens overnemen', exact=True).click()
            expect(first_choice).not_to_be_checked()
            expect(page.locator('.issue-confirmation')).to_contain_text('Nergens overgenomen')
            page.get_by_role('button', name='Volgende', exact=True).click()
            second_choice = page.locator('.chunk-issue-item input[type=checkbox]')
            expect(second_choice).not_to_be_checked()
            expect(page.locator('.issue-confirmation')).to_contain_text('Nergens overgenomen')

            # A single occurrence can be enabled again as an exception.
            second_choice.check()
            page.get_by_role('button', name='Vorige', exact=True).click()
            expect(page.locator('.chunk-issue-item input[type=checkbox]')).not_to_be_checked()
            page.get_by_role('button', name='Volgende', exact=True).click()
            page.get_by_role('button', name='Niet verbeteren', exact=True).click()
            expect(page.locator('.chunk-issue-item input[type=checkbox]')).not_to_be_checked()
            with page.expect_download(predicate=lambda download: download.suggested_filename == 'sample-gecorrigeerd.pdf'):
                page.locator('#download-btn').click()
            assert len(exports[-1]['chunks']) == 2
            assert all(chunk['revised_text'] == TEXT for chunk in exports[-1]['chunks'])
            second_choice.check()
            with page.expect_download(predicate=lambda download: download.suggested_filename == 'sample-gecorrigeerd.pdf'):
                page.locator('#download-btn').click()
            assert exports[-1]['chunks'][0]['revised_text'] == TEXT
            assert 'spelfoutt' not in exports[-1]['chunks'][1]['revised_text']
            assert [chunk['page_index'] for chunk in exports[-1]['chunks']] == [0, 1]
            page.route('**/download/*', lambda route: route.fulfill(
                status=409, headers={'X-Missing-Font': 'MetaBook-Caps'},
                json={'detail': 'Lettertype ontbreekt.'}))
            page.locator('#download-btn').click()
            font_input = page.get_by_label('Lettertype MetaBook-Caps toevoegen', exact=False)
            expect(font_input).to_be_visible()
            font_input.set_input_files({'name': 'meta.otf', 'mimeType': 'font/otf', 'buffer': b'font'})
            page.get_by_label('Toch gebruiken voor MetaBook-Caps', exact=False).check()
            def font_upload(route):
                assert 'name="override"\r\n\r\ntrue' in route.request.post_data
                route.fulfill(json={'font_name': 'MetaBook-Caps', 'override': True})
            page.route('**/fonts/upload', font_upload)
            page.get_by_role('button', name='Lettertype uploaden', exact=True).click()
            expect(page.get_by_role('status').filter(has_text='MetaBook-Caps is toegevoegd')).to_be_visible()
            expect(second_choice).to_be_checked()
            assert not errors, errors
            browser.close()
            print('Browser: sensitivity, per-place rejection and document-wide rejection passed.')
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == '__main__':
    run()
