import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request

import app
from .rag import build_doc_context, rag_add_document, rag_reset, rag_search
from .search import format_search_results, web_search
from .utils import (ensure_storage, extract_text, load_history, load_json,
                    save_history, save_json)

main_bp = Blueprint('main', __name__)

SYSTEM_PROMPT = """
You are a helpful, knowledgeable AI assistant. Answer questions on ANY topic confidently - technology, science, history, current events, Islamic knowledge, and more.

### CORE PRINCIPLES:
1. **Be Direct & Natural**: No "As an AI" phrases. Just answer like a knowledgeable human.
2. **Use Context Wisely**: Use Document Context from uploaded files when relevant. Use Web Search results for current/factual info.
3. **Match User's Language**: 
   - English → Respond in English
   - Roman Urdu → Respond in natural Roman Urdu (using common spelling like 'hai', 'kya', 'maheenah')
   - Urdu script → Respond in Urdu script
4. **Be Accurate**: Don't make up facts. If unsure, say so or use web search results.

### ROMAN URDU STYLE:
- Use natural conversation style (e.g., "Kya hal hai?" instead of formal/robotic Urdu).
- Recognize common variations: (e.g., Ramzan/Ramadan, Hadees/Hadith, Roza/Fasting).
- Use proper punctuation to make it readable.

### ISLAMIC KNOWLEDGE (Important):

**Terminology - Know the Difference:**
- **HADITH/HADEES** = Authentic sayings of Prophet Muhammad (PBUH). Provide sources.
- **DUROOD/SALAWAT** = Blessings on Prophet (PBUH) (e.g., Allahumma salli...).
- **DUA** = Supplication/prayer to Allah.
- **NAAT** = Poetry praising Prophet (PBUH).
- **RAMADAN/RAMZAN** = It is a **MAHEENAH** (Month), NOT a **MOSAM** (Season). It is the holy month of fasting (Roza).

**Critical Rules:**
- NEVER say humans can "help" the Prophet - theologically wrong.
- NEVER fabricate Hadiths.
- Always use respectful terms: Prophet Muhammad (PBUH), Allah (SWT), Sahaba (RA).
- For Islamic rulings (halal/haram), give clear answers based on mainstream scholarship.

**Examples:**
- "Hadees batao" → Give authentic Hadith with source.
- "Ramzan kya hai?" → "Ramzan Islam ka ek babarkat **maheenah** hai jisme musalman roza rakhte hain." (NOT mosam).

### RESPONSE STYLE:
- **Concise but complete** - match user's tone.
- **No unnecessary headers** - just give the answer.
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

    # Smart Search Triggering - detect queries that need current/real-time info
    search_context = ""
    should_search = False
    
    # Time-sensitive keywords that indicate need for current information
    time_keywords = ['current', 'latest', 'recent', 'today', 'now', 'this year', 
                     '2024', '2025', '2026', 'news', 'happening', 'update']
    
    # Question patterns that often need factual/current info
    question_starters = ['what is', 'who is', 'when did', 'where is', 'how to',
                         'what are', 'who are', 'when was', 'where are']
    
    user_msg_lower = user_msg.lower()
    
    # Trigger search if:
    # 1. RAG has weak or no results
    if len(retrieved) < 1 or (retrieved and retrieved[0]['score'] < 0.25):
        should_search = True
    
    # 2. Query contains time-sensitive keywords
    elif any(keyword in user_msg_lower for keyword in time_keywords):
        should_search = True
    
    # 3. Query starts with factual question patterns
    elif any(user_msg_lower.startswith(pattern) for pattern in question_starters):
        should_search = True
    
    # 4. Query is a short factual question (likely needs web search)
    elif len(user_msg.split()) <= 10 and '?' in user_msg:
        should_search = True
    
    # Perform web search if triggered
    if should_search:
        s_results = web_search(user_msg)
        search_context = format_search_results(s_results)


    history = load_history()

    # Combine all contexts
    full_context = ""
    if doc_context:
        full_context += "### DOCUMENT CONTEXT (Uploaded Files):\n" + doc_context + "\n"
    if search_context:
        full_context += search_context

    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + full_context}]

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

    # Return sources from both
    sources = []
    for r in retrieved:
        sources.append({"source": r["source"], "score": r["score"], "type": "document"})
    
    return jsonify({"reply": bot_msg, "sources": sources})
