"""Run with the bundled Windows Python; verifies the actual local services."""
from pathlib import Path
import subprocess
import sys

import fitz
import httpx

root = Path(sys.executable).resolve().parent.parent
process = subprocess.Popen([sys.executable, str(root / 'desktop.py')], cwd=root,
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding='utf-8', errors='replace')
try:
    for line in process.stdout:
        print(line, end='', flush=True)
        if line.startswith('Open zo nodig zelf: '):
            url = line.split(': ', 1)[1].strip()
            break
    else:
        raise RuntimeError('Launcher stopped before it was ready')
    with httpx.Client(base_url=url, timeout=120) as client:
        response = client.post('/upload', files={'file': ('proef.txt', b'Dit is een spelfoutt.', 'text/plain')})
        response.raise_for_status()
        document = response.json()
        assert document['issues'], document
        chunks = [dict(original_text=c['text'], revised_text=c['text'].replace('spelfoutt', 'spelfout'),
                       start=c['start'], page_index=c.get('page_index')) for c in document['chunks']]
        response = client.post('/download/' + document['stored_name'],
                               json=dict(file_name='proef.txt', chunks=chunks))
        response.raise_for_status()
        assert response.text == 'Dit is een spelfout.'
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((40, 70), 'Dit is een spelfoutt.', fontsize=14, color=(0.8, 0.3, 0.1))
            raw = pdf.tobytes()
        response = client.post('/upload', files={'file': ('proef.pdf', raw, 'application/pdf')})
        response.raise_for_status()
        document = response.json()
        chunk = document['chunks'][0]
        edited = dict(original_text=chunk['text'], revised_text=chunk['text'].replace('spelfoutt', 'spelfout'),
                      page_index=0)
        response = client.post('/comparison-pdf', json=dict(stored_name=document['stored_name'], **edited))
        response.raise_for_status()
        response = client.post('/download/' + document['stored_name'], json=dict(file_name='proef.pdf', chunks=[edited]))
        response.raise_for_status()
        with fitz.open(stream=response.content, filetype='pdf') as pdf:
            assert 'spelfoutt' not in pdf[0].get_text()
            assert 'spelfout' in pdf[0].get_text()
    print('WINDOWS SMOKE PASSED: local LanguageTool, TXT correction, PDF preview and PDF download.', flush=True)
finally:
    if process.poll() is None:
        process.communicate('\n', timeout=40)
    assert process.returncode == 0, process.returncode
