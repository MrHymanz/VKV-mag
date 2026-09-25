const uploadForm = document.getElementById('upload-form');
const fileInput = document.getElementById('file-input');
const statusBox = document.getElementById('status');
const issueList = document.getElementById('issue-list');
const documentText = document.getElementById('document-text');
const downloadBtn = document.getElementById('download-btn');

let currentDocumentText = '';
let currentFileName = '';

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

        statusBox.textContent = `Controle afgerond: ${data.issues.length} suggesties.`;
        currentDocumentText = data.text;
        currentFileName = data.file_name;
        documentText.value = data.text;
        issueList.innerHTML = '';

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
