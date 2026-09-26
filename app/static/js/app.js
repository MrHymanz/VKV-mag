const uploadForm = document.getElementById('upload-form');
const fileInput = document.getElementById('file-input');
const statusBox = document.getElementById('status');
const issueList = document.getElementById('issue-list');
const documentText = document.getElementById('document-text');
const chunkReview = document.getElementById('chunk-review');
const downloadBtn = document.getElementById('download-btn');
const uploadPanel = document.getElementById('upload-panel');
const issuesPanel = document.getElementById('issues-panel');
const pdfPreviewPanel = document.getElementById('pdf-preview-panel');
const pdfPreviewFrame = document.getElementById('pdf-preview-frame');

function setReviewMode(enabled) {
    document.body.classList.toggle('review-mode', enabled);
    if (enabled) {
        uploadPanel?.classList.add('is-hidden');
        issuesPanel?.classList.add('is-hidden');
    } else {
        uploadPanel?.classList.remove('is-hidden');
        issuesPanel?.classList.remove('is-hidden');
    }
}

let currentDocumentText = '';
let currentFileName = '';
let currentStoredName = '';
let reviewChunks = [];
let currentChunkIndex = 0;

function buildRevisedChunkText(chunk) {
    const chunkText = chunk && typeof chunk.text === 'string' ? chunk.text : '';
    if (!chunkText || !Array.isArray(chunk.issues) || chunk.issues.length === 0) {
        return chunkText;
    }

    const edits = [...chunk.issues]
        .filter((issue) => issue && typeof issue === 'object')
        .map((issue) => {
            const chunkStart = Number(chunk.start || 0);
            const issueOffset = Number(issue.offset || 0);
            const issueLength = Math.max(Number(issue.length || 0), 0);
            const start = Math.max(0, issueOffset - chunkStart);
            const end = Math.min(chunkText.length, start + issueLength);
            const replacement = issue.replacements && issue.replacements.length ? issue.replacements[0].value : '';
            const originalSlice = chunkText.slice(start, end);
            const normalizedOriginal = originalSlice.replace(/\s+/g, ' ').trim();
            const normalizedReplacement = String(replacement || '').replace(/\s+/g, ' ').trim();

            if (!replacement || normalizedReplacement === normalizedOriginal) {
                return null;
            }

            return { start, end, replacement };
        })
        .filter(Boolean)
        .filter((edit) => edit.start >= 0 && edit.end >= edit.start)
        .sort((a, b) => a.start - b.start);

    if (edits.length === 0) {
        return chunkText;
    }

    let result = '';
    let cursor = 0;

    for (const edit of edits) {
        result += chunkText.slice(cursor, edit.start);
        result += edit.replacement;
        cursor = edit.end;
    }

    result += chunkText.slice(cursor);
    return result;
}

function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;').replace(/'/g, '&#039;');
}

function buildDiffMarkup(originalText, revisedText, issues) {
    const ranges = (issues || [])
        .map((issue) => {
            const start = Math.max(0, Number(issue.offset || 0));
            const end = Math.max(start, Number(issue.length || 0) + start);
            const replacement = issue.replacements && issue.replacements.length ? issue.replacements[0].value : '';
            const originalSlice = originalText.slice(start, end);
            const normalizedOriginal = originalSlice.replace(/\s+/g, ' ').trim();
            const normalizedReplacement = String(replacement || '').replace(/\s+/g, ' ').trim();
            if (!replacement || normalizedReplacement === normalizedOriginal) {
                return null;
            }
            return { start, end, replacement };
        })
        .filter(Boolean)
        .filter((range) => range.end > range.start || range.replacement)
        .sort((a, b) => a.start - b.start);

    const renderOriginal = (baseText) => {
        if (ranges.length === 0) {
            return escapeHtml(baseText);
        }

        let html = '';
        let cursor = 0;

        ranges.forEach(({ start, end }) => {
            html += escapeHtml(baseText.slice(cursor, start));
            html += `<span class="diff-removed">${escapeHtml(baseText.slice(start, end))}</span>`;
            cursor = end;
        });

        html += escapeHtml(baseText.slice(cursor));
        return html;
    };

    const renderRevised = (baseText) => {
        if (ranges.length === 0) {
            return escapeHtml(baseText);
        }

        let html = '';
        let cursor = 0;

        ranges.forEach(({ start, end, replacement }) => {
            html += escapeHtml(baseText.slice(cursor, start));
            html += `<span class="diff-added">${escapeHtml(replacement || baseText.slice(start, end))}</span>`;
            cursor = end;
        });

        html += escapeHtml(baseText.slice(cursor));
        return html;
    };

    return {
        originalHtml: renderOriginal(originalText),
        revisedHtml: renderRevised(revisedText),
    };
}

function renderChunks(chunks) {
    reviewChunks = Array.isArray(chunks) ? chunks : [];
    currentChunkIndex = Math.min(currentChunkIndex, Math.max(0, reviewChunks.length - 1));
    chunkReview.innerHTML = '';

    if (reviewChunks.length === 0) {
        return;
    }

    const approvedCount = reviewChunks.filter((chunk) => chunk.approved).length;
    const openCount = reviewChunks.length - approvedCount;

    const summary = document.createElement('div');
    summary.className = 'chunk-summary';
    summary.textContent = `Samenvatting: ${approvedCount} van ${reviewChunks.length} delen goedgekeurd • ${openCount} open`;
    chunkReview.appendChild(summary);

    const chunk = reviewChunks[currentChunkIndex];
    const card = document.createElement('section');
    card.className = 'chunk-card';
    if (chunk.approved) {
        card.classList.add('approved');
    }

    const header = document.createElement('div');
    header.className = 'chunk-card-header';
    header.innerHTML = `
        <div class="chunk-header-copy">
            <strong>Controle deel ${chunk.id} van ${reviewChunks.length}</strong>
            <span class="chunk-status ${chunk.approved ? 'approved' : 'open'}">${chunk.approved ? 'Goedgekeurd' : 'Open voor controle'}</span>
        </div>
        <button type="button" class="secondary">${chunk.approved ? 'Goedkeuring intrekken' : 'Deel goedkeuren'}</button>
    `;

    const approveBtn = header.querySelector('button');
    approveBtn.addEventListener('click', async () => {
        const nextState = !chunk.approved;
        chunk.approved = nextState;

        if (currentStoredName) {
            try {
                await fetch('/approve-chunk', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        stored_name: currentStoredName,
                        chunk_id: chunk.id,
                        approved: nextState,
                    }),
                });
            } catch (error) {
                console.error('Chunk status kon niet worden opgeslagen.', error);
            }
        }

        renderChunks(reviewChunks);
        statusBox.textContent = chunk.approved ? `Deel ${chunk.id} goedgekeurd.` : `Controle voor deel ${chunk.id} opnieuw open.`;
    });

    const nav = document.createElement('div');
    nav.className = 'chunk-nav';
    nav.innerHTML = `
        <button type="button" class="nav-button" ${currentChunkIndex === 0 ? 'disabled' : ''}>Vorige</button>
        <span>Deel ${currentChunkIndex + 1} / ${reviewChunks.length}</span>
        <button type="button" class="nav-button" ${currentChunkIndex === reviewChunks.length - 1 ? 'disabled' : ''}>Volgende</button>
        <button type="button" class="nav-button secondary-btn" id="pdf-compare-btn">PDF vergelijken</button>
    `;

    const pdfCompareBtn = nav.querySelector('#pdf-compare-btn');
    pdfCompareBtn.addEventListener('click', async () => {
        const originalText = chunk.text || '';
        const revisedText = buildRevisedChunkText(chunk);
        const response = await fetch('/comparison-pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                original_text: originalText,
                revised_text: revisedText,
                file_name: currentFileName || 'document.pdf',
                stored_name: currentStoredName || '',
                page_index: currentChunkIndex,
            }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'PDF-vergelijking kon niet worden gemaakt.' }));
            throw new Error(error.detail || 'PDF-vergelijking kon niet worden gemaakt.');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        if (pdfPreviewFrame) {
            pdfPreviewFrame.src = url;
            pdfPreviewPanel?.classList.remove('is-hidden');
            pdfPreviewPanel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            statusBox.textContent = `PDF-vergelijking voor deel ${chunk.id} wordt hieronder getoond.`;
        } else {
            const a = document.createElement('a');
            a.href = url;
            a.download = `${currentFileName || 'document'}-vergelijking.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            statusBox.textContent = `PDF-vergelijking voor deel ${chunk.id} gedownload.`;
        }
        window.setTimeout(() => window.URL.revokeObjectURL(url), 10000);
    });

    nav.querySelectorAll('.nav-button').forEach((button, index) => {
        button.addEventListener('click', () => {
            if (button.textContent === 'Vorige') {
                if (currentChunkIndex > 0) {
                    currentChunkIndex -= 1;
                }
            } else if (button.textContent === 'Volgende') {
                if (currentChunkIndex < reviewChunks.length - 1) {
                    currentChunkIndex += 1;
                }
            }
            renderChunks(reviewChunks);
        });
    });

    const comparePanel = document.createElement('div');
    comparePanel.className = 'compare-panel';

    const originalCompare = document.createElement('div');
    originalCompare.className = 'compare-column';
    const originalTitle = document.createElement('div');
    originalTitle.className = 'compare-title';
    originalTitle.textContent = 'Originele PDF pagina';
    const originalText = document.createElement('div');
    originalText.className = 'compare-text';
    const diffMarkup = buildDiffMarkup(chunk.text || '', buildRevisedChunkText(chunk), chunk.issues || []);
    originalText.innerHTML = diffMarkup.originalHtml;
    originalCompare.appendChild(originalTitle);
    originalCompare.appendChild(originalText);

    const revisedCompare = document.createElement('div');
    revisedCompare.className = 'compare-column revised';
    const revisedTitle = document.createElement('div');
    revisedTitle.className = 'compare-title';
    revisedTitle.textContent = 'Aangepaste PDF pagina';
    const revisedText = document.createElement('div');
    revisedText.className = 'compare-text';
    revisedText.innerHTML = diffMarkup.revisedHtml;
    revisedCompare.appendChild(revisedTitle);
    revisedCompare.appendChild(revisedText);

    comparePanel.appendChild(originalCompare);
    comparePanel.appendChild(revisedCompare);

    const textBox = document.createElement('div');
    textBox.className = 'chunk-card-text';
    textBox.textContent = chunk.text || '';

    const issueListEl = document.createElement('ul');
    issueListEl.className = 'chunk-issue-list';

    if (!chunk.issues || chunk.issues.length === 0) {
        const emptyItem = document.createElement('li');
        emptyItem.className = 'chunk-issue-item';
        emptyItem.textContent = 'Geen problemen in dit deel.';
        issueListEl.appendChild(emptyItem);
    } else {
        chunk.issues.forEach((issue) => {
            const item = document.createElement('li');
            item.className = 'chunk-issue-item';
            const suggestion = issue.replacements && issue.replacements.length
                ? issue.replacements.map((replacement) => replacement.value).join(', ')
                : 'Geen suggestie';
            const category = issue.display_category || issue.category || 'Controle';
            const rule = issue.display_rule || issue.rule_id || 'algemeen';
            item.innerHTML = `
                <div class="issue-meta">
                    <strong>${category}</strong>
                    <span>${rule}</span>
                </div>
                <div class="issue-text">${issue.message || issue.short_message || 'Geen uitleg beschikbaar.'}</div>
                <div class="issue-suggestion">Suggestie: ${suggestion}</div>
            `;
            issueListEl.appendChild(item);
        });
    }

    card.appendChild(header);
    card.appendChild(nav);
    card.appendChild(comparePanel);
    card.appendChild(textBox);
    card.appendChild(issueListEl);
    chunkReview.appendChild(card);
}

uploadForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const file = fileInput.files[0];
    if (!file) {
        statusBox.textContent = 'Kies eerst een document.';
        return;
    }

    statusBox.textContent = 'Document wordt gecontroleerd...';
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData,
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || 'Controle mislukt.');
        }

        const chunks = (data.chunks || []).map((chunk) => ({ ...chunk, approved: chunk.approved ?? chunk.issues?.length === 0 }));

        statusBox.textContent = `Controle afgerond: ${data.issues.length} suggesties. ${chunks.length} delen gecontroleerd.`;
        currentDocumentText = data.text;
        currentFileName = data.file_name;
        currentStoredName = data.stored_name;
        documentText.value = data.text;
        setReviewMode(true);
        issueList.innerHTML = '';
        renderChunks(chunks);

        if (data.issues.length === 0) {
            const item = document.createElement('li');
            item.textContent = 'Geen taalproblemen gevonden.';
            issueList.appendChild(item);
            downloadBtn.disabled = false;
            return;
        }

        data.issues.forEach((issue, index) => {
            const item = document.createElement('li');
            item.className = 'issue-item';
            item.innerHTML = `
                <strong>Probleem ${index + 1}: ${issue.category}</strong>
                <div>${issue.message || issue.short_message || 'Geen uitleg beschikbaar.'}</div>
                <div>Context: ${issue.context || ''}</div>
                <div>Suggestie: ${issue.replacements.length ? issue.replacements.map(r => r.value).join(', ') : 'Geen suggestie'}</div>
            `;
            item.addEventListener('click', () => {
                const start = issue.offset || 0;
                const length = issue.length || 0;
                if (!issue.replacements.length) {
                    return;
                }
                const replacement = issue.replacements[0].value;
                fetch('/apply-correction', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: currentDocumentText,
                        start,
                        length,
                        replacement,
                    }),
                }).then((res) => res.json()).then((json) => {
                    currentDocumentText = json.corrected_text;
                    documentText.value = json.corrected_text;
                    statusBox.textContent = 'Correctie toegepast.';
                });
            });
            issueList.appendChild(item);
        });

        downloadBtn.disabled = false;
    } catch (error) {
        statusBox.textContent = error.message;
        console.error(error);
    }
});

downloadBtn.addEventListener('click', () => {
    if (!currentFileName) {
        return;
    }
    window.location.href = `/download/${encodeURIComponent(currentFileName)}`;
});
