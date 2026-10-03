from __future__ import annotations

import shutil
import uuid
import hashlib
import json
import fitz
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    ALLOWED_EXTENSIONS,
    APP_HOST,
    APP_PORT,
    DEFAULT_LANGUAGE,
    LANGUAGETOOL_TIMEOUT_SECONDS,
    LANGUAGETOOL_URL,
    MAX_UPLOAD_MB,
    TEMP_DIR,
    UPLOAD_DIR,
)
from app.parsers.docx_parser import DocxParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.txt_parser import TxtParser
from app.services.correction_service import apply_correction
from app.services.document_export import ExportRequest, export_document
from app.services.languagetool import LanguageToolClient
from app.services.pdf_preview import build_comparison_pdf_preview
from app.services.pdf_text_style import FONT_DIR, MissingFontError, font_matches, override_path

app = FastAPI(title="VKV Documentcontrole", version="0.1.0")
REVIEW_STATES: dict[str, dict[int, bool]] = {}

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.post("/fonts/upload")
async def upload_font(file: UploadFile = File(...), expected_font: str = Form(...), override: bool = Form(False)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".otf", ".ttf"}:
        raise HTTPException(400, "Kies een OTF- of TTF-fontbestand.")
    contents = await file.read(10 * 1024 * 1024 + 1)
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(413, "Het fontbestand mag maximaal 10 MB groot zijn.")
    if contents[:4] not in {b"OTTO", b"\x00\x01\x00\x00", b"true"}:
        raise HTTPException(400, "Dit is geen geldig OTF- of TTF-fontbestand.")
    try:
        font = fitz.Font(fontbuffer=contents)
    except Exception as exc:
        raise HTTPException(400, "Het fontbestand kan niet worden gelezen.") from exc
    if not expected_font.strip() or len(expected_font) > 200:
        raise HTTPException(400, "Ongeldige fontnaam.")
    if not override and not font_matches(contents, expected_font, font.name):
        raise HTTPException(400, f'Dit bestand bevat {font.name}; verwacht wordt {expected_font}. Kies de juiste variant.')
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    target = FONT_DIR / (hashlib.sha256(contents).hexdigest() + suffix)
    temporary = FONT_DIR / (uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(contents)
        temporary.replace(target)
        if override:
            temporary.write_text(json.dumps({'file': target.name, 'expected': expected_font, 'actual': font.name}))
            temporary.replace(override_path(FONT_DIR, expected_font))
    finally:
        temporary.unlink(missing_ok=True)
    return {"font_name": font.name, "override": override}

PARSER_MAP = {
    ".txt": TxtParser(),
    ".docx": DocxParser(),
    ".pdf": PdfParser(),
}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    sensitivity: Literal["cautious", "normal", "strict"] = Form("cautious"),
) -> dict[str, Any]:
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
    lt = LanguageToolClient(base_url=LANGUAGETOOL_URL, timeout=LANGUAGETOOL_TIMEOUT_SECONDS, sensitivity=sensitivity)
    try:
        if parsed.file_type == "pdf":
            chunks = []
            start = 0
            for page_index, text in enumerate(parsed.metadata["pages"]):
                page_issues = []
                for checked in lt.check_document_chunks(text, language=DEFAULT_LANGUAGE):
                    for issue in checked["issues"]:
                        page_issues.append({**issue, "offset": issue["offset"] + start})
                chunks.append({
                    "id": page_index + 1,
                    "page_index": page_index,
                    "text": text,
                    "start": start,
                    "issues": page_issues,
                })
                start += len(text) + 1
        else:
            chunks = lt.check_document_chunks(parsed.text, language=DEFAULT_LANGUAGE)
        issues = [issue for chunk in chunks for issue in chunk["issues"]]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    for chunk in chunks:
        chunk["approved"] = not chunk["issues"]

    REVIEW_STATES[upload_path.name] = {chunk["id"]: chunk["approved"] for chunk in chunks}
    parsed.issues = issues
    return {
        "file_name": Path(file.filename).name,
        "stored_name": upload_path.name,
        "file_type": parsed.file_type,
        "sensitivity": sensitivity,
        "text": parsed.text,
        "issues": issues,
        "chunks": chunks,
    }


@app.post("/approve-chunk")
async def approve_chunk(payload: dict[str, Any]) -> dict[str, Any]:
    stored_name = str(payload.get("stored_name", "")).strip()
    chunk_id = int(payload.get("chunk_id", -1))
    approved = bool(payload.get("approved", False))

    if not stored_name:
        raise HTTPException(status_code=400, detail="stored_name ontbreekt.")
    if chunk_id < 0:
        raise HTTPException(status_code=400, detail="chunk_id is ongeldig.")

    path = UPLOAD_DIR / stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document niet gevonden.")

    review_state = REVIEW_STATES.setdefault(stored_name, {})
    review_state[chunk_id] = approved
    return {"stored_name": stored_name, "chunk_id": chunk_id, "approved": approved}


@app.post("/apply-correction")
async def apply_correction_route(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text", "")
    start = int(payload.get("start", 0))
    length = int(payload.get("length", 0))
    replacement = str(payload.get("replacement", ""))
    corrected = apply_correction(text, start, length, replacement)
    return {"corrected_text": corrected}


@app.post("/comparison-pdf")
async def create_comparison_pdf(payload: dict[str, Any]) -> FileResponse:
    original_text = str(payload.get("original_text", ""))
    revised_text = str(payload.get("revised_text", ""))
    document_name = str(payload.get("file_name", "document"))
    stored_name = str(payload.get("stored_name", ""))
    original_pdf_path = UPLOAD_DIR / stored_name if stored_name else None

    if not original_pdf_path and not original_text and not revised_text:
        raise HTTPException(status_code=400, detail="Geen tekst beschikbaar voor PDF-vergelijking.")

    safe_name = f"{uuid.uuid4().hex}-comparison.pdf"
    preview_path = TEMP_DIR / safe_name
    page_index = int(payload.get("page_index", 0))
    warnings = []
    try:
        build_comparison_pdf_preview(
            original_pdf_path, revised_text, preview_path,
            page_index=page_index, original_text=original_text, warnings=warnings,
        )
    except MissingFontError as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers={"X-Missing-Font": exc.font_name}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    document_base = Path(document_name).stem or "document"
    return FileResponse(
        preview_path,
        media_type="application/pdf",
        filename=f"{document_base}-vergelijking.pdf",
        headers={"X-Document-Warning": " ".join(dict.fromkeys(warnings))} if warnings else None,
    )


@app.get("/download/{stored_name}")
async def download_document(stored_name: str) -> FileResponse:
    raise HTTPException(status_code=409, detail="Ververs de pagina en gebruik de downloadknop om uw gekozen correcties mee te nemen.")


@app.post("/download/{stored_name}")
async def download_corrected_document(stored_name: str, payload: ExportRequest) -> FileResponse:
    file_path = (UPLOAD_DIR / stored_name).resolve()
    if file_path.parent != UPLOAD_DIR.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Document niet gevonden.")
    suffix = file_path.suffix.lower()
    export_path = TEMP_DIR / f"{uuid.uuid4().hex}-gecorrigeerd{suffix}"
    warnings = []
    try:
        export_document(file_path, payload.chunks, export_path, warnings=warnings)
    except MissingFontError as exc:
        export_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(exc), headers={"X-Missing-Font": exc.font_name}) from exc
    except ValueError as exc:
        export_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    media_types = {
        ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return FileResponse(export_path, media_type=media_types.get(suffix, "application/octet-stream"),
                        filename=f"{Path(payload.file_name).stem}-gecorrigeerd{suffix}",
                        headers={"X-Document-Warning": " ".join(dict.fromkeys(warnings))} if warnings else None)


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
