import os
from datetime import datetime
from flask import Blueprint, current_app, jsonify, render_template, request

import app
from .rag import build_doc_context, rag_add_document, rag_reset, rag_search
from .search import format_search_results, web_search
from .utils import (
    ensure_storage,
    extract_text,
    load_history,
    save_history,
    save_json,
    load_state,
    save_state
)

main_bp = Blueprint("main", __name__)

SYSTEM_PROMPT = """
You are a warm, intelligent, human-like assistant.
You respond the way a thoughtful, friendly person would — not like a textbook or a robot.

Your default style:
- Natural
- Calm
- Helpful
- To-the-point
- Friendly (but not childish)

You NEVER explain yourself unless asked.
You NEVER say you are an AI.
You NEVER give long answers unless the user clearly wants detail.

──────────────── SMALL TALK & GREETINGS ────────────────

If the user's message is a greeting or casual check-in:
1. GREETINGS (hi, hello, assalam o alaikum):
   - Reply with a warm, short greeting.
   - "Assalam o alaikum" → "Wa alaikum assalam!"
2. STATUS/GRATITUDE (how are you, alhamdulillah, I am good):
   - "Alhamdulillah" or "I am good" means the user is fine.
   - Reply warmly: "Great to hear that!" or "Alhamdulillah, glad you're doing well."
   - DO NOT say "Wa alaikum assalam" to "Alhamdulillah".

Rules:
- Reply in MAX 1–2 short lines.
- Be warm and human.
- No explanations or introductions.
- Match the user's name/vibe but respect the language lock.

This rule OVERRIDES everything else for short messages.

────────────────── LANGUAGE SENSE (PRIMARY) ──────────────────

English is your PRIMARY language. You should default to English unless the user specifically uses Roman Urdu or Urdu script.

Decide language ONLY from the latest user message:
- Clear English → Reply ONLY in English
- Clear Roman Urdu → Reply ONLY in Roman Urdu
- Urdu script → Reply ONLY in Urdu script
- Mixed → Favor English unless Urdu is dominant
- If unsure → ALWAYS Default to English

Ignore past language completely. Respect the SESSION LOCK if provided in final instructions.

──────────────── ROMAN URDU UNDERSTANDING ────────────────

Understand messy Roman Urdu without complaining:
hai / hy / ha
kya / kia
mujhe / mjhy / mjy
bana rha hu / bana rah hn
chaiye / chahiye
alhamdulillah (any spelling)

Respond in clean, natural Roman Urdu.
Sound like a real person, not a translation.

──────────────── HOW TO ANSWER ────────────────

Default behavior:
- Simple question → Short answer
- Normal question → Clear paragraph
- Confused user → Explain gently
- Curious user → Go deeper
- Emotional tone → Acknowledge softly

Never over-explain.
Never lecture.
Never show off.

──────────────── KNOWLEDGE RULES ────────────────

- Never invent facts
- Never fake sources
- Say “not sure” if needed
- Use web/search only for current info

──────────────── ISLAMIC CONTENT (WHEN ASKED) ────────────────

Be respectful and authentic.
Use:
- Allah (SWT)
- Prophet Muhammad (PBUH)
- Sahaba (RA)

Never fabricate Hadith.
Mention source when sharing Hadith.
Ramadan is a MAHEENAH, not a mosam.

──────────────── FINAL GOAL ────────────────

Sound like a smart, kind human friend.
Helpful > fancy.
Natural > perfect.
Short > long (unless asked).
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
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt"]:
        return jsonify({"error": "Only PDF, DOCX, or TXT allowed"}), 400

    path = os.path.join(current_app.config["UPLOAD_DIR"], f.filename)
    f.save(path)

    try:
        text = extract_text(path)
        added = rag_add_document(f.filename, text)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True, "chunks_added": added})

@main_bp.get("/status")
def status():
    """Debug info for RAG and API status."""
    from .rag import HAS_RAG_DEPS
    import app
    
    rag_status = "Ready" if (HAS_RAG_DEPS and app.embedder is not None) else "Disabled"
    if HAS_RAG_DEPS and app.embedder is None:
        rag_status = "Embedder Not Initialized"
    elif not HAS_RAG_DEPS:
        rag_status = "Missing Libraries (faiss/numpy)"

    return jsonify({
        "api_client": "Connected" if app.client else "Missing Key",
        "rag_support": rag_status,
        "torch_version": os.popen("pip show torch | grep Version").read().strip() or "Not found",
        "faiss_version": os.popen("pip show faiss-cpu | grep Version").read().strip() or "Not found"
    })

@main_bp.post("/reset_docs")
def reset_docs():
    rag_reset()
    return jsonify({"ok": True})

@main_bp.post("/clear_history")
def clear_history():
    save_json(current_app.config["HISTORY_FILE"], [])
    return jsonify({"ok": True})

@main_bp.post("/chat")
def chat():
    body = request.get_json(force=True)
    user_msg = (body.get("message") or "").strip()

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    # -------- LANGUAGE LOCK --------
    lang_state = load_state(current_app.config["LANG_STATE_FILE"])
    
    # Default to English if not set (as requested by user)
    if "forced_language" not in lang_state:
        lang_state["forced_language"] = "english"
        save_state(current_app.config["LANG_STATE_FILE"], lang_state)
    
    forced_lang = lang_state.get("forced_language")
    msg_lower = user_msg.lower()

    if any(cmd in msg_lower for cmd in ["only english", "english only", "speak english", "talk in english"]):
        lang_state["forced_language"] = "english"
        save_state(current_app.config["LANG_STATE_FILE"], lang_state)
        return jsonify({"reply": "Got it 👍 I’ll reply in English only from now on."})

    if any(cmd in msg_lower for cmd in ["only roman", "roman only", "roman urdu only", "speak roman", "talk in roman"]):
        lang_state["forced_language"] = "roman"
        save_state(current_app.config["LANG_STATE_FILE"], lang_state)
        return jsonify({"reply": "Theek hai 👍 Ab main Roman Urdu mein hi jawab doon ga."})

    if any(cmd in msg_lower for cmd in ["auto language", "language auto", "reset language", "detect language"]):
        lang_state["forced_language"] = None
        save_state(current_app.config["LANG_STATE_FILE"], lang_state)
        return jsonify({"reply": "Language reset ho gayi 👍 Ab main auto-detect karoon ga."})

    # -------- RAG --------
    print(f"[CHAT] Query: {user_msg}")
    retrieved = rag_search(user_msg)
    print(f"[CHAT] RAG retrieved {len(retrieved)} matches.")
    doc_context = build_doc_context(retrieved)

    # -------- SMART SEARCH --------
    search_context = ""
    should_search = False

    user_lower = user_msg.lower()
    time_words = ["latest", "current", "today", "news", "update", "2024", "2025", "2026"]

    if not retrieved or retrieved[0]["score"] < 0.25:
        should_search = True
    elif any(w in user_lower for w in time_words):
        should_search = True
    elif "?" in user_msg and len(user_msg.split()) <= 10:
        should_search = True

    if should_search:
        results = web_search(user_msg)
        search_context = format_search_results(results)

    # -------- CONTEXT --------
    full_context = ""
    if doc_context:
        full_context += "DOC CONTEXT:\n" + doc_context + "\n"
    if search_context:
        full_context += search_context

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n" + full_context}
    ]

    if forced_lang == "english":
        messages.append({
            "role": "system",
            "content": "IMPORTANT: The user has locked the language to ENGLISH. You MUST reply ONLY in English, regardless of input."
        })
    elif forced_lang == "roman":
        messages.append({
            "role": "system",
            "content": "IMPORTANT: The user has locked the language to ROMAN URDU. You MUST reply ONLY in Roman Urdu, regardless of input."
        })

    # -------- HISTORY (FILTER SMALL TALK) --------
    history = load_history()
    recent = history[-8:] if len(history) > 8 else history

    for h in recent:
        if len(h["user"].split()) <= 6:
            continue
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["bot"]})

    # -------- FINAL OVERRIDE --------
    lang_instruction = "Match the user's language strictly."
    if forced_lang == "english":
        lang_instruction = "IMPORTANT: Language is LOCKED to ENGLISH. Do NOT use any other language."
    elif forced_lang == "roman":
        lang_instruction = "IMPORTANT: Language is LOCKED to ROMAN URDU. Do NOT use any other language."

    messages.append({
        "role": "system",
        "content": (
            "FINAL REMINDER:\n"
            "- Greetings → max 2 short lines.\n"
            "- Never introduce yourself.\n"
            "- Never say you are an AI.\n"
            f"- {lang_instruction}\n"
            "- Be natural and concise."
        )
    })

    messages.append({"role": "user", "content": user_msg})

    # -------- SAFETY CHECK --------
    if app.client is None:
        return jsonify({
            "error": "GROQ_API_KEY is missing. Please add it to your Railway project variables.",
            "reply": "⚠️ System Error: My brain (API Key) is missing. Please add the GROQ_API_KEY to Railway variables to continue."
        }), 500

    try:
        completion = app.client.chat.completions.create(
            model=current_app.config["MODEL"],
            messages=messages,
            temperature=0.35,
            max_tokens=900
        )
        bot_msg = completion.choices[0].message.content.strip()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    history.append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "user": user_msg,
        "bot": bot_msg
    })
    save_history(history)

    sources = [
        {"source": r["source"], "score": r["score"], "type": "document"}
        for r in retrieved
    ]

    return jsonify({"reply": bot_msg, "sources": sources})
