const uploadForm = document.getElementById('upload-form');
const fileInput = document.getElementById('file-input');
const sensitivitySelect = document.getElementById('sensitivity');
const sensitivityHelp = document.getElementById('sensitivity-help');
const reviewSettings = document.getElementById('review-settings');
const reviewSettingsBtn = document.getElementById('review-settings-btn');
const sensitivityLabels = { cautious: 'Voorzichtig', normal: 'Normaal', strict: 'Streng' };
const sensitivityDescriptions = {
    cautious: 'Twijfelachtige woordvervangingen worden overgeslagen. Controleer ook spellingssuggesties voordat u een deel goedkeurt.',
    normal: 'Grammatica en interpunctie worden ook gecontroleerd. Deze suggesties neemt u alleen over door ze aan te vinken.',
    strict: 'Ook stijl en mogelijke woordkeuzes worden getoond. Twijfelachtige suggesties blijven ongewijzigd totdat u ze aanvinkt.',
};
try {
    const savedSensitivity = localStorage.getItem('vkv-sensitivity');
    if (Object.hasOwn(sensitivityLabels, savedSensitivity)) sensitivitySelect.value = savedSensitivity;
} catch (_) { /* Storage can be disabled in the browser. */ }
sensitivityHelp.textContent = sensitivityDescriptions[sensitivitySelect.value];
sensitivitySelect.addEventListener('change', () => {
    try { localStorage.setItem('vkv-sensitivity', sensitivitySelect.value); } catch (_) {}

    sensitivityHelp.textContent = sensitivityDescriptions[sensitivitySelect.value];
});
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
        document.getElementById('result-panel').appendChild(statusBox);
        uploadPanel?.classList.add('is-hidden');
        issuesPanel?.classList.add('is-hidden');
    } else {
        uploadPanel?.appendChild(statusBox);
        uploadPanel?.classList.remove('is-hidden');
        issuesPanel?.classList.remove('is-hidden');
    }
}

let currentDocumentText = '';
let currentFileName = '';
let currentStoredName = '';
let reviewChunks = [];
let currentChunkIndex = 0;

let previewVersion = 0;
function invalidatePdfPreview() {
    previewVersion += 1;
    pdfPreviewPanel?.classList.add('is-hidden');
    pdfPreviewFrame?.removeAttribute('src');
}

reviewSettingsBtn.addEventListener('click', () => {
    setReviewMode(false);
    sensitivitySelect.focus();
    uploadPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    statusBox.textContent = 'Kies de gevoeligheid en klik op Document controleren. Uw eerdere keuzes worden bij de nieuwe controle gewist.';
});

function suggestionKey(chunk, issue) {
    const start = Number(issue.offset) - Number(chunk.start || 0);
    const original = chunk.text.slice(start, start + Number(issue.length));
    const replacement = issue.replacements?.[issue.selectedReplacement ?? 0]?.value;
    return JSON.stringify([issue.rule_id, original.normalize('NFC'), replacement]);
}

function updateReviewChoices(chunks, message) {
    const changedChunks = [...new Set(chunks)];
    changedChunks.forEach((chunk) => { chunk.approved = false; });
    invalidatePdfPreview();
    renderChunks(reviewChunks);
    statusBox.textContent = message;
    if (currentStoredName) {
        Promise.all(changedChunks.map(async (chunk) => {
            const response = await fetch('/approve-chunk', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stored_name: currentStoredName, chunk_id: chunk.id, approved: false }),
            });
            if (!response.ok) throw new Error('Goedkeuringsstatus kon niet worden opgeslagen.');
        })).catch((error) => { statusBox.textContent = `${message} ${error.message}`; });
    }
}

function declineEverywhere(sourceChunk, sourceIssue) {
    const key = suggestionKey(sourceChunk, sourceIssue);
    const affected = [];
    let count = 0;
    for (const chunk of reviewChunks) {
        for (const issue of chunk.issues || []) {
            if (suggestionKey(chunk, issue) !== key) continue;
            issue.accepted = false;
            issue.rejectedEverywhere = true;
            affected.push(chunk);
            count += 1;
        }
    }
    updateReviewChoices(affected, `Deze suggestie wordt op ${count} plekken in dit document niet overgenomen. Klik op PDF vergelijken voor de bijgewerkte weergave.`);
}

function selectedEdits(text, issues, chunkStart = 0) {
    const candidates = (issues || [])
        .filter((issue) => issue.accepted === true)
        .map((issue) => {
            const start = Number(issue.offset) - chunkStart;
            const end = start + Number(issue.length);
            const replacement = issue.replacements?.[issue.selectedReplacement ?? 0]?.value;
            if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end > text.length
                || typeof replacement !== 'string' || replacement === text.slice(start, end)) return null;
            return { start, end, replacement };
        })
        .filter(Boolean)
        .sort((a, b) => a.start - b.start);
    const edits = [];
    let cursor = 0;
    for (const edit of candidates) {
        if (edit.start < cursor) continue;
        edits.push(edit);
        cursor = edit.end;
    }
    return edits;
}

function buildRevisedChunkText(chunk) {
    const text = chunk?.text || '';
    let result = '';
    let cursor = 0;
    for (const edit of selectedEdits(text, chunk?.issues, Number(chunk?.start || 0))) {
        result += text.slice(cursor, edit.start) + edit.replacement;
        cursor = edit.end;
    }
    return result + text.slice(cursor);
}

function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;').replace(/'/g, '&#039;');
}

function buildDiffMarkup(originalText, revisedText, issues) {
    const ranges = selectedEdits(originalText, issues);

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
            html += `<span class="diff-added">${escapeHtml(replacement)}</span>`;
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
        const requestVersion = previewVersion;
        try {
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
                    page_index: chunk.page_index ?? currentChunkIndex,
                }),
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'PDF-vergelijking kon niet worden gemaakt.' }));
                throw new Error(error.detail || 'PDF-vergelijking kon niet worden gemaakt.');
            }

            const blob = await response.blob();
            if (requestVersion !== previewVersion) return;
            const url = window.URL.createObjectURL(blob);
            if (pdfPreviewFrame) {
                pdfPreviewFrame.src = url;
                pdfPreviewPanel?.classList.remove('is-hidden');
                pdfPreviewPanel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                statusBox.textContent = `PDF-vergelijking voor deel ${chunk.id} wordt hieronder getoond. ${response.headers.get('X-Document-Warning') || ''}`;
            } else {
                const a = document.createElement('a');
                a.href = url;
                a.download = `${currentFileName || 'document'}-vergelijking.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                statusBox.textContent = `PDF-vergelijking voor deel ${chunk.id} gedownload. ${response.headers.get('X-Document-Warning') || ''}`;
            }
            window.setTimeout(() => window.URL.revokeObjectURL(url), 10000);
        } catch (error) {
            if (requestVersion !== previewVersion) return;
            statusBox.textContent = error.message;
            pdfPreviewPanel?.classList.add('is-hidden');
            if (pdfPreviewFrame) pdfPreviewFrame.removeAttribute('src');
        }
    });

    nav.querySelectorAll('.nav-button:not(#pdf-compare-btn)').forEach((button, index) => {
        button.addEventListener('click', () => {
            invalidatePdfPreview();
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
    const localIssues = (chunk.issues || []).map((issue) => ({
        ...issue, offset: issue.offset - (chunk.start || 0),
    }));
    const diffMarkup = buildDiffMarkup(chunk.text || '', chunk.text || '', localIssues);
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
                    <strong>${escapeHtml(category)}</strong>
                    <span>${escapeHtml(rule)}</span>
                </div>
                <div class="issue-text">${escapeHtml(issue.message || issue.short_message || 'Geen uitleg beschikbaar.')}</div>
                <div class="issue-suggestion">Suggestie: ${escapeHtml(suggestion)}</div>
            `;
            if (issue.replacements?.length) {
                const choice = document.createElement('label');
                choice.className = 'issue-choice';
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = issue.accepted === true;
                const label = document.createElement('span');
                const start = issue.offset - (chunk.start || 0);
                label.textContent = `Overnemen: “${chunk.text.slice(start, start + issue.length)}” →`;
                const select = document.createElement('select');
                select.setAttribute('aria-label', 'Vervanging kiezen');
                issue.replacements.forEach((replacement, index) => {
                    const option = document.createElement('option');
                    option.value = index;
                    option.textContent = replacement.value === '' ? '(verwijderen)' : replacement.value;
                    select.appendChild(option);
                });
                select.value = issue.selectedReplacement ?? 0;
                const updateChoice = () => {
                    issue.accepted = checkbox.checked;
                    issue.selectedReplacement = Number(select.value);
                    issue.rejectedEverywhere = false;
                    updateReviewChoices([chunk], 'Keuze bijgewerkt. Klik op PDF vergelijken om de aangepaste weergave te bekijken.');
                };
                checkbox.addEventListener('change', updateChoice);
                select.addEventListener('change', updateChoice);
                choice.append(checkbox, label);
                const actions = document.createElement('div');
                actions.className = 'issue-actions';
                const decline = document.createElement('button');
                decline.type = 'button';
                decline.className = 'secondary';
                decline.textContent = 'Niet verbeteren';
                decline.title = 'Alleen deze plek ongewijzigd laten';
                decline.addEventListener('click', () => {
                    issue.accepted = false;
                    issue.rejectedEverywhere = false;
                    updateReviewChoices([chunk], 'Deze plek blijft ongewijzigd. Andere plekken behouden hun eigen keuze.');
                });
                const declineAll = document.createElement('button');
                declineAll.type = 'button';
                declineAll.className = 'secondary';
                declineAll.textContent = 'Nergens overnemen';
                declineAll.title = 'Dezelfde tekst en vervanging bij deze regel op alle pagina’s uitvinken';
                declineAll.addEventListener('click', () => declineEverywhere(chunk, issue));
                actions.append(decline, declineAll);
                item.append(choice, select, actions);
                if (!issue.accepted) {
                    const notice = document.createElement('span');
                    notice.className = 'issue-confirmation';
                    notice.textContent = issue.rejectedEverywhere
                        ? 'Nergens overgenomen in dit document. U kunt deze plek opnieuw aanvinken als uitzondering.'
                        : 'Niet toegepast — alleen overnemen als deze suggestie hier klopt.';
                    item.appendChild(notice);
                }
            }
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

    const submitButton = uploadForm.querySelector('button[type=submit]');
    submitButton.disabled = true;
    statusBox.textContent = 'Document wordt gecontroleerd...';
    const formData = new FormData();
    formData.append('file', file);
    formData.append('sensitivity', sensitivitySelect.value);

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData,
        });

        const data = await response.json().catch(() => {
            throw new Error(`De server kon de upload niet verwerken (HTTP ${response.status}). Probeer het opnieuw of neem contact op met de beheerder.`);
        });
        if (!response.ok) {
            throw new Error(data.detail || 'Controle mislukt.');
        }

        const chunks = (data.chunks || []).map((chunk) => ({ ...chunk, approved: chunk.approved ?? chunk.issues?.length === 0 }));

        statusBox.textContent = `Controle afgerond: ${data.issues.length} suggesties. ${chunks.length} delen gecontroleerd.`;
        currentDocumentText = data.text;
        currentFileName = file.name;
        currentStoredName = data.stored_name;
        documentText.value = data.text;
        invalidatePdfPreview();
        reviewSettings.textContent = `Gevoeligheid: ${sensitivityLabels[data.sensitivity]}. Alleen aangevinkte suggesties worden in de vergelijking toegepast.`;
        reviewSettings.classList.remove('is-hidden');
        reviewSettingsBtn.classList.remove('is-hidden');
        setReviewMode(true);
        issueList.innerHTML = '';
        currentChunkIndex = 0;
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
                <div>${escapeHtml(issue.message || issue.short_message || 'Geen uitleg beschikbaar.')}</div>
                <div>Context: ${issue.context || ''}</div>
                <div>Suggestie: ${issue.replacements.length ? issue.replacements.map(r => r.value).join(', ') : 'Geen suggestie'}</div>
            `;
            issueList.appendChild(item);
        });

        downloadBtn.disabled = false;
    } catch (error) {
        statusBox.textContent = error.message;
        console.error(error);
    } finally {
        submitButton.disabled = false;
    }
});

downloadBtn.addEventListener('click', async () => {
    if (!currentStoredName) {
        return;
    }
    const fileName = currentFileName;
    const payload = {
        file_name: fileName,
        chunks: reviewChunks.map((chunk) => ({
            original_text: chunk.text || '',
            revised_text: buildRevisedChunkText(chunk),
            page_index: chunk.page_index ?? null,
            start: chunk.start || 0,
        })),
    };
    downloadBtn.disabled = true;
    statusBox.textContent = 'Document met de aangevinkte correcties wordt gemaakt...';
    try {
        const response = await fetch(`/download/${encodeURIComponent(currentStoredName)}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(typeof error.detail === 'string' ? error.detail : 'Het aangepaste document kon niet worden gemaakt.');
        }
        const url = window.URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = url;
        const dot = fileName.lastIndexOf('.');
        link.download = `${dot < 0 ? fileName : fileName.slice(0, dot)}-gecorrigeerd${dot < 0 ? '' : fileName.slice(dot)}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);
        statusBox.textContent = `Het document met de aangevinkte correcties is gedownload. ${response.headers.get('X-Document-Warning') || ''}`;
    } catch (error) {
        statusBox.textContent = error.message;
    } finally {
        downloadBtn.disabled = false;
    }
});
