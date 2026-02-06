import os
import uuid
from typing import List, Dict
from flask import current_app
import app
from .utils import load_json, save_json

# Optional imports for light deployment
try:
    import faiss
    import numpy as np
    HAS_RAG_DEPS = True
except ImportError:
    faiss = None
    np = None
    HAS_RAG_DEPS = False

def chunk_text(text: str) -> List[str]:
    chunk_size = current_app.config['CHUNK_SIZE']
    overlap = current_app.config['CHUNK_OVERLAP']
    
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
        i += max(1, chunk_size - overlap)
    return chunks

def embed_texts(texts: List[str]):
    # returns float32 matrix [n, d]
    if not HAS_RAG_DEPS or app.embedder is None:
        return None
    vectors = app.embedder.encode(texts, normalize_embeddings=True)
    return np.array(vectors, dtype=np.float32)

def load_faiss_index(dim: int):
    if not HAS_RAG_DEPS:
        return None
    faiss_file = current_app.config['FAISS_FILE']
    if os.path.exists(faiss_file):
        return faiss.read_index(faiss_file)
    # cosine similarity via inner product on normalized embeddings
    return faiss.IndexFlatIP(dim)

def save_faiss_index(index):
    if not HAS_RAG_DEPS or index is None:
        return
    faiss.write_index(index, current_app.config['FAISS_FILE'])

def rag_add_document(filename: str, full_text: str) -> int:
    """Adds document chunks to FAISS + chunks.json. Returns number of chunks added."""
    print(f"[RAG] Adding document: {filename} ({len(full_text)} chars)")
    if not HAS_RAG_DEPS or app.embedder is None:
        print("WARNING: RAG dependencies missing or embedder not initialized.")
        return 0

    chunks = chunk_text(full_text)
    print(f"[RAG] Created {len(chunks)} chunks.")
    if not chunks:
        return 0

    chunks_file = current_app.config['CHUNKS_FILE']
    chunk_objs = load_json(chunks_file, [])
    
    # prepare new chunk objects with metadata
    new_objs = []
    for c in chunks:
        new_objs.append({
            "id": str(uuid.uuid4()),
            "source": filename,
            "text": c
        })

    # embeddings
    print("[RAG] Generating embeddings...")
    vecs = embed_texts([o["text"] for o in new_objs])
    if vecs is None:
        print("[RAG] ERROR: Embedding failed (vecs is None)")
        return 0
        
    dim = vecs.shape[1]
    index = load_faiss_index(dim)

    index.add(vecs)
    print(f"[RAG] Added to FAISS index. Total docs in index: {index.ntotal}")

    # persist
    chunk_objs.extend(new_objs)
    save_json(chunks_file, chunk_objs)
    save_faiss_index(index)
    print("[RAG] Successfully saved index and chunks.")
    return len(new_objs)

def rag_reset():
    print("[RAG] Resetting all knowledge...")
    # wipe chunks + index
    save_json(current_app.config['CHUNKS_FILE'], [])
    faiss_file = current_app.config['FAISS_FILE']
    if os.path.exists(faiss_file):
        os.remove(faiss_file)

def rag_search(query: str, k: int = None) -> List[Dict]:
    if not HAS_RAG_DEPS or app.embedder is None:
        return []

    if k is None:
        k = current_app.config['TOP_K']
        
    SIMILARITY_THRESHOLD = 0.20  # Ignore very low relevance matches
    
    chunks_file = current_app.config['CHUNKS_FILE']
    chunk_objs = load_json(chunks_file, [])
    if not chunk_objs:
        print("[RAG] Search skipped: chunks.json is empty or missing.")
        return []

    # embed query
    qv = embed_texts([query])
    if qv is None:
        return []
        
    dim = qv.shape[1]
    index = load_faiss_index(dim)

    if index is None or index.ntotal == 0:
        print("[RAG] Search skipped: FAISS index is empty.")
        return []

    print(f"[RAG] Searching index with {index.ntotal} items...")
    scores, idxs = index.search(qv, k)
    idxs = idxs[0].tolist()
    scores = scores[0].tolist()

    results = []
    for rank, (i, s) in enumerate(zip(idxs, scores), start=1):
        if i < 0 or i >= len(chunk_objs):
            continue
        
        # Filter by threshold
        if float(s) < SIMILARITY_THRESHOLD:
            continue
            
        item = chunk_objs[i].copy()
        item["score"] = float(s)
        item["rank"] = rank
        results.append(item)
    
    print(f"[RAG] Found {len(results)} matches above threshold {SIMILARITY_THRESHOLD}.")
    return results

def build_doc_context(retrieved: List[Dict]) -> str:
    if not HAS_RAG_DEPS or app.embedder is None:
        return "DOCUMENT CONTEXT: (RAG features are disabled in this deployment)"
        
    if not retrieved:
        return "DOCUMENT CONTEXT: (no documents uploaded yet)"
    lines = ["DOCUMENT CONTEXT (top matches):"]
    for r in retrieved:
        # keep context compact but readable
        snippet = r["text"].strip()
        if len(snippet) > 2500: 
            snippet = snippet[:2500] + "..."
        lines.append(f"[{r['rank']}] Source: {r['source']} | Score: {r['score']:.3f}\n{snippet}")
    return "\n\n".join(lines)
