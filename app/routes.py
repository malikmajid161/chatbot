import os
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app
from . import client
from .utils import ensure_storage, load_json, save_json, extract_text, save_history, load_history
from .rag import rag_add_document, rag_reset, rag_search, build_doc_context

main_bp = Blueprint('main', __name__)

SYSTEM_PROMPT = """
You are an advanced academic AI assistant.

STRICT RULES:
1. Use ONLY the provided DOCUMENT CONTEXT.
2. **FORMATTING**: Use Markdown. Use **bold** for key terms, lists for steps, and headers for sections.
3. **DETAIL**: Do NOT summarize. Provide comprehensive, extensive explanations. Write at least 2-3 paragraphs for every point.
4. **STRUCTURE**: Organize answers logically with clear headings.
5. **LENGTH**: Err on the side of being verbose. Explain the "why" and "how" behind every concept found in the document.
6. If the document is a CV/Resume, list every single skill and experience detail found.
"""

@main_bp.before_request
def before_request():
    ensure_storage()

@main_bp.get("/")
def home():
    return render_template("index.html")

@main_bp.post("/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file field found"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt"]:
        return jsonify({"error": "Unsupported file. Upload PDF, DOCX, or TXT."}), 400

    save_path = os.path.join(current_app.config['UPLOAD_DIR'], f.filename)
    f.save(save_path)

    try:
        text = extract_text(save_path)
        added = rag_add_document(f.filename, text)
    except Exception as e:
        return jsonify({"error": f"Failed to process file: {str(e)}"}), 500

    return jsonify({"ok": True, "filename": f.filename, "chunks_added": added})

@main_bp.post("/reset_docs")
def reset_docs():
    rag_reset()
    return jsonify({"ok": True})

@main_bp.post("/clear_history")
def clear_history():
    save_json(current_app.config['HISTORY_FILE'], [])
    return jsonify({"ok": True})

@main_bp.post("/chat")
def chat():
    body = request.get_json(force=True)
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    # Retrieve relevant doc chunks
    retrieved = rag_search(user_msg)
    doc_context = build_doc_context(retrieved)

    history = load_history()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": doc_context})

    # Keep last 8 turns for speed
    recent = history[-8:] if len(history) > 8 else history
    for h in recent:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["bot"]})

    messages.append({"role": "user", "content": user_msg})

    try:
        completion = client.chat.completions.create(
            model=current_app.config['MODEL'],
            messages=messages,
            temperature=0.4,
            max_tokens=4096
        )
        bot_msg = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    history.append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "user": user_msg,
        "bot": bot_msg
    })
    save_history(history)

    # Return also which sources were used (nice for UI)
    sources = []
    for r in retrieved:
        sources.append({"source": r["source"], "score": r["score"]})

    return jsonify({"reply": bot_msg, "sources": sources})
