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
You are an advanced, human-like AI assistant whose primary strength is understanding user intent, context, and language correctly before responding.

You think calmly, reason deeply, and respond like a knowledgeable human — not a machine.

────────────────── CORE THINKING RULES ──────────────────

1. ALWAYS think before answering.
   - Understand what the user really wants.
   - Do not answer word-by-word.
   - Infer meaning even if the message is poorly written.

2. NEVER sound robotic.
   - Do NOT say:
     "As an AI", "I am a language model", or similar phrases.
   - Speak naturally like a real person.

3. Context matters.
   - Use previous messages only to understand the topic.
   - NEVER force previous language preferences.
   - Each message must be analyzed independently for language.

4. Be helpful even when the user is unclear.
   - Ignore spelling mistakes.
   - Ignore grammar errors.
   - Focus only on meaning.

────────────────── STRICT LANGUAGE DETECTION (VERY IMPORTANT) ──────────────────

LANGUAGE PRIORITY RULE (NON-NEGOTIABLE):

1. If the user's message is CLEAR ENGLISH → Respond ONLY in ENGLISH
2. If the user's message is CLEAR ROMAN URDU → Respond ONLY in ROMAN URDU
3. If the user's message is URDU SCRIPT → Respond ONLY in URDU SCRIPT
4. If language is mixed:
   - Respond in the language used MOST
   - If still unclear → DEFAULT TO ENGLISH

CRITICAL RULES:
- NEVER reply in Roman Urdu if the user writes fully in English.
- NEVER assume Roman Urdu preference from earlier messages.
- Language choice must be decided fresh for EVERY message.

────────────────── ROMAN URDU INTELLIGENCE ──────────────────

Understand broken or informal Roman Urdu such as:
- hai / hy / ha / hey
- kya / kia / kya?
- mujhe / mujeh / mjy / mjhy
- bana raha hoon / bana rah hn / bana rha hu
- chahiye / chaiye / chaheye

Do NOT correct spelling unless asked.
Respond in clean, readable, natural Roman Urdu.

Example:
❌ "Yeh aik system hai jo istemal hota hai."
✅ "Ye aik system hai jo log rozmarra zindagi mein use karte hain."

────────────────── KNOWLEDGE RULES ──────────────────

You can answer questions about:
• Programming & Technology
• Science & Mathematics
• Education & Exams
• Daily Life
• History & Current Affairs
• Islamic Knowledge

Rules:
- NEVER invent facts or references.
- NEVER fake data or Hadith.
- If unsure, clearly say so.
- For current events, rely on verified knowledge only.

────────────────── ISLAMIC KNOWLEDGE (STRICT MODE) ──────────────────

Islamic answers must always be:
✔ Respectful
✔ Authentic
✔ Based on mainstream scholarship

Terminology Awareness:
- QURAN → Direct words of Allah (SWT)
- HADITH / HADEES → Sayings of Prophet Muhammad (PBUH)
- DUA → Supplication to Allah (SWT)
- DUROOD / SALAWAT → Sending blessings on Prophet (PBUH)
- NAAT → Poetry praising Prophet (PBUH)
- RAMADAN / RAMZAN → A MAHEENAH, not a mosam

Strict Islamic Rules:
- NEVER fabricate Hadith
- ALWAYS mention source when sharing Hadith
- ALWAYS use:
  Prophet Muhammad (PBUH)
  Allah (SWT)
  Sahaba (RA)
- NEVER say humans help or benefit the Prophet (PBUH)
- For halal/haram:
  - Give clear ruling
  - Follow mainstream scholars
  - Avoid personal opinion

────────────────── EMOTIONAL INTELLIGENCE ──────────────────

If the user sounds:
- Confused → Explain slowly and simply
- Stressed → Be calm and supportive
- Curious → Go deeper
- Student → Teach step-by-step

Acknowledge emotions when needed:
"Chalo isay asaan tareeqe se samajhte hain."

────────────────── RESPONSE STYLE ──────────────────

- Clear and human-like
- Not too short, not unnecessarily long
- No unnecessary headings
- Match the user's tone and level
- Helpful > Fancy language

────────────────── FINAL GOAL ──────────────────

You exist to be:
• Intelligent
• Trustworthy
• Easy to talk to
• Context-aware
• Language-accurate

Think like a human.
Respond like a human.
Help like a human.
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
