const uploadForm = document.getElementById('upload-form');
const fileInput = document.getElementById('file-input');
const statusBox = document.getElementById('status');
const issueList = document.getElementById('issue-list');
const documentText = document.getElementById('document-text');
const chunkReview = document.getElementById('chunk-review');
const downloadBtn = document.getElementById('download-btn');

let currentDocumentText = '';
let currentFileName = '';
let currentStoredName = '';

function renderChunks(chunks) {
    chunkReview.innerHTML = '';
    if (!Array.isArray(chunks) || chunks.length === 0) {
        return;
    }

    chunks.forEach((chunk) => {
        const card = document.createElement('section');
        card.className = 'chunk-card';
        if (chunk.approved) {
            card.classList.add('approved');
        }

        const header = document.createElement('div');
        header.className = 'chunk-card-header';
        header.innerHTML = `
            <div class="chunk-header-copy">
                <strong>Controle deel ${chunk.id}</strong>
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

            renderChunks(chunks);
            statusBox.textContent = chunk.approved ? `Deel ${chunk.id} goedgekeurd.` : `Controle voor deel ${chunk.id} opnieuw open.`;
        });

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
                item.innerHTML = `
                    <div class="issue-meta">
                        <strong>${issue.category || 'Controle'}</strong>
                        <span>${issue.rule_id || 'algemeen'}</span>
                    </div>
                    <div class="issue-text">${issue.message || issue.short_message || 'Geen uitleg beschikbaar.'}</div>
                    <div class="issue-suggestion">Suggestie: ${suggestion}</div>
                `;
                issueListEl.appendChild(item);
            });
        }

        card.appendChild(header);
        card.appendChild(textBox);
        card.appendChild(issueListEl);
        chunkReview.appendChild(card);
    });
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

        statusBox.textContent = `Controle afgerond: ${data.issues.length} suggesties. ${data.chunks?.length || 0} delen gecontroleerd.`;
        currentDocumentText = data.text;
        currentFileName = data.file_name;
        currentStoredName = data.stored_name;
        documentText.value = data.text;
        issueList.innerHTML = '';
        renderChunks(data.chunks || []);

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
