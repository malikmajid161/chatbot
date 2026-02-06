import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request

import app
from .rag import build_doc_context, rag_add_document, rag_reset, rag_search
from .utils import (ensure_storage, extract_text, load_history, load_json,
                    save_history, save_json)

main_bp = Blueprint('main', __name__)

SYSTEM_PROMPT = """
You are a helpful and intelligent AI assistant. 

### CORE GUIDELINES:
1. **Be Natural**: Respond to greetings (like "hi", "how are you", "kese ho") naturally and briefly.
2. **Contextual Accuracy**: If Document Context is provided, use it to answer questions accurately. If no context is provided or relevant, answer based on your general knowledge but mention if you are doing so.
3. **Conciseness**: Match the user's length. If they ask a short question, give a direct and focused answer. Avoid unnecessary preamble or "Possible Interpretations" lists unless requested.
4. **Formatting**: Use Markdown for readability (**bolding**, lists, etc.).
5. **Detail**: Only provide extensive details and paragraphs if the user asks a complex question or if the provided document requires deep explanation.

### URDU & REGIONAL CONTEXT:
6. **Script Detection**: Respond in the same script the user uses. 
   - If they use Urdu script (اردو), respond in Urdu script.
   - If they use Roman Urdu (e.g., "kese ho"), respond in Roman Urdu.
   - If they explicitly ask for a script (e.g., "urdu mai roman mai nai"), strictly follow that instruction.
7. **Poetry Genres**: Distinguish between general poetry (**Nazm/Ghazal**) and religious poetry (**Naat** - praise of the Prophet Muhammad). If a user asks for a Naat, do not provide a romantic poem or general Nazm.
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

    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + doc_context}]

    # Keep last 8 turns for speed
    recent = history[-8:] if len(history) > 8 else history
    for h in recent:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["bot"]})

    messages.append({"role": "user", "content": user_msg})

    try:
        completion = app.client.chat.completions.create(
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
