import os
import json
import docx2txt
from pypdf import PdfReader
from flask import current_app

def ensure_storage():
    """Ensures data directories and files exist."""
    data_dir = current_app.config['DATA_DIR']
    rag_dir = current_app.config['RAG_DIR']
    history_file = current_app.config['HISTORY_FILE']
    chunks_file = current_app.config['CHUNKS_FILE']
    upload_dir = current_app.config['UPLOAD_DIR']

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(rag_dir, exist_ok=True)
    os.makedirs(upload_dir, exist_ok=True)

    if not os.path.exists(history_file):
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump([], f)

    if not os.path.exists(chunks_file):
        with open(chunks_file, "w", encoding="utf-8") as f:
            json.dump([], f)

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_history():
    return load_json(current_app.config['HISTORY_FILE'], [])

def save_history(history):
    save_json(current_app.config['HISTORY_FILE'], history)

def load_state(path):
    return load_json(path, {})

def save_state(path, data):
    save_json(path, data)

def extract_text_from_pdf(filepath: str) -> str:
    reader = PdfReader(filepath)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)

def extract_text_from_docx(filepath: str) -> str:
    return docx2txt.process(filepath) or ""

def extract_text_from_txt(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def extract_text(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    if ext == ".docx":
        return extract_text_from_docx(filepath)
    if ext == ".txt":
        return extract_text_from_txt(filepath)
    raise ValueError("Unsupported file type. Use PDF, DOCX, or TXT.")
