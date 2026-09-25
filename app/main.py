from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    ALLOWED_EXTENSIONS,
    APP_HOST,
    APP_PORT,
    DEFAULT_LANGUAGE,
    LANGUAGETOOL_URL,
    MAX_UPLOAD_MB,
    TEMP_DIR,
    UPLOAD_DIR,
)
from app.parsers.docx_parser import DocxParser
from app.parsers.txt_parser import TxtParser
from app.services.correction_service import apply_correction
from app.services.languagetool import LanguageToolClient

app = FastAPI(title="VKV Documentcontrole", version="0.1.0")

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

PARSER_MAP = {
    ".txt": TxtParser(),
    ".docx": DocxParser(),
}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Bestand ontbreekt.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Niet-ondersteund bestandstype: {suffix}")

    file_size = getattr(file, "size", None)
    if file_size and file_size > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Bestand is te groot.")

    safe_name = f"{uuid.uuid4().hex}{suffix}"
    upload_path = UPLOAD_DIR / safe_name
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Bestand is te groot.")
    upload_path.write_bytes(contents)

    parser = PARSER_MAP.get(suffix)
    if parser is None:
        raise HTTPException(status_code=400, detail="Geen parser beschikbaar voor dit bestandstype.")

    parsed = parser.parse(upload_path)
    lt = LanguageToolClient(base_url=LANGUAGETOOL_URL)
    try:
        issues = lt.check_text(parsed.text, language=DEFAULT_LANGUAGE)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    normalized = [lt.normalize_issue(match) for match in issues]
    parsed.issues = normalized
    return {
        "file_name": parsed.file_name,
        "stored_name": upload_path.name,
        "file_type": parsed.file_type,
        "text": parsed.text,
        "issues": normalized,
    }


@app.post("/apply-correction")
async def apply_correction_route(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text", "")
    start = int(payload.get("start", 0))
    length = int(payload.get("length", 0))
    replacement = str(payload.get("replacement", ""))
    corrected = apply_correction(text, start, length, replacement)
    return {"corrected_text": corrected}


@app.get("/download/{stored_name}")
async def download_document(stored_name: str) -> FileResponse:
    file_path = UPLOAD_DIR / stored_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document niet gevonden.")

    original_name = file_path.stem
    return FileResponse(file_path, media_type="application/octet-stream", filename=f"{original_name}-gecorrigeerd{file_path.suffix}")


@app.on_event("shutdown")
async def cleanup_temp_files() -> None:
    for item in UPLOAD_DIR.iterdir():
        if item.is_file():
            item.unlink(missing_ok=True)
    for item in TEMP_DIR.iterdir():
        if item.is_file():
            item.unlink(missing_ok=True)
    for directory in (UPLOAD_DIR, TEMP_DIR):
        if directory.exists():
            for child in directory.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
