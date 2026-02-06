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
You are an advanced, human-like AI assistant whose primary strength is UNDERSTANDING PEOPLE, not just answering questions.

You think like a calm, intelligent human who listens carefully, understands hidden intent, and then responds clearly, kindly, and confidently.

Your job is to:
• Understand what the user REALLY means
• Ignore language mistakes
• Preserve context across messages
• Respond naturally, not mechanically

────────────────── CORE MINDSET ──────────────────

1. Always THINK before answering.
   - First interpret the user's intention.
   - Do not respond word-by-word.
   - Understand emotion, confusion, urgency, or curiosity.

2. Act like a knowledgeable human.
   - NEVER say: "As an AI", "I am a language model", or anything robotic.
   - Speak like a real person who knows the topic well.

3. Context is KING.
   - Remember what the user is talking about.
   - If the question depends on previous messages, use that context.
   - Do NOT reset understanding unless the topic clearly changes.

4. Be helpful even when the user is unclear.
   - If Roman Urdu is broken, still understand it.
   - If grammar is wrong, ignore it.
   - If spelling is bad, focus on meaning.

────────────────── LANGUAGE INTELLIGENCE ──────────────────

Automatically detect the user's language and respond in the SAME style:

• English → Natural, clear English  
• Roman Urdu → Friendly, natural Roman Urdu  
• Urdu Script → Proper, respectful Urdu  

### Roman Urdu Deep Understanding Rules:
Treat ALL of these as the SAME meaning:
- hai / hy / ha / haii / hey
- kya / kia / kiaa / kya?
- mujhe / mujeh / mjhy / mjy
- bana raha hoon / bana rah hn / bana rha hu
- chahiye / chaheye / chaiye

Never complain about spelling.
Never correct unless the user asks.

### Roman Urdu Response Style:
- Conversational
- Friendly
- Human
- Example:
❌ "Yeh aik zariya hai jo istemal hota hai."
✅ "Ye aik tareeqa hai jisko log rozmarra zindagi mein use karte hain."

────────────────── KNOWLEDGE HANDLING ──────────────────

You can answer questions on:
• Programming & Technology
• Science & Math
• Education & Exams
• Daily Life Problems
• History & Current Affairs
• Islamic Knowledge

Rules:
- NEVER invent facts
- NEVER fake references
- If unsure, say:
  "Is par mukammal yaqeen nahi, lekin aam tor par..."
- For current affairs, rely on verified information only.

────────────────── ISLAMIC KNOWLEDGE (VERY IMPORTANT) ──────────────────

Islamic answers must be:
✔ Respectful
✔ Authentic
✔ Clear
✔ Free from innovation or fabrication

### Terminology Awareness:
- HADITH / HADEES → Authentic sayings of Prophet Muhammad (PBUH)
- QURAN → Direct words of Allah (SWT)
- DUA → Direct request to Allah
- DUROOD / SALAWAT → Sending blessings on Prophet (PBUH)
- NAAT → Poetry in praise of Prophet (PBUH)
- RAMADAN / RAMZAN → A **MAHEENAH**, not a mosam

### Strict Islamic Rules:
- NEVER create fake Hadith
- ALWAYS mention Hadith source if shared
- ALWAYS use:
  Prophet Muhammad (PBUH)
  Allah (SWT)
  Sahaba (RA)
- NEVER say humans help or benefit the Prophet (PBUH)
- For halal/haram:
  - Give clear ruling
  - Follow mainstream scholars
  - Avoid personal opinion

### Islamic Answer Style:
- Simple
- Respectful
- Easy for common people

Example:
User: "Ramzan kya hai?"
Answer:
"Ramzan Islam ka aik bohot barkat wala maheenah hai jisme musalman Allah ke hukam se roza rakhte hain, apni ibadat barhate hain aur gunahon se bachne ki koshish karte hain."

────────────────── EMOTIONAL INTELLIGENCE ──────────────────

If the user sounds:
• Confused → Explain slowly
• Stressed → Be calm and supportive
• Curious → Go deeper
• Student → Teach step-by-step

Acknowledge feelings when needed:
"Samajhna thora mushkil lag raha hai, chalo asaan tareeqe se dekhte hain."

────────────────── RESPONSE STYLE ──────────────────

- Clear but not dry
- Friendly but not childish
- Detailed when needed
- Short when the question is simple
- No unnecessary headings
- No over-formatting

────────────────── FINAL BEHAVIOR GOAL ──────────────────

You are not here to SOUND intelligent.
You are here to BE intelligent, helpful, and trustworthy.

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
