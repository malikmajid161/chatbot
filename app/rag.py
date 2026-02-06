import os
import uuid
import faiss
import numpy as np
from typing import List, Dict
from flask import current_app
import app
from .utils import load_json, save_json

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

def embed_texts(texts: List[str]) -> np.ndarray:
    # returns float32 matrix [n, d]
    if app.embedder is None:
        raise ValueError("Embedder is not initialized. Ensure create_app() has been called.")
    vectors = app.embedder.encode(texts, normalize_embeddings=True)
    return np.array(vectors, dtype=np.float32)

def load_faiss_index(dim: int):
    faiss_file = current_app.config['FAISS_FILE']
    if os.path.exists(faiss_file):
        return faiss.read_index(faiss_file)
    # cosine similarity via inner product on normalized embeddings
    return faiss.IndexFlatIP(dim)

def save_faiss_index(index):
    faiss.write_index(index, current_app.config['FAISS_FILE'])

def rag_add_document(filename: str, full_text: str) -> int:
    """Adds document chunks to FAISS + chunks.json. Returns number of chunks added."""
    chunks = chunk_text(full_text)
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
    vecs = embed_texts([o["text"] for o in new_objs])
    dim = vecs.shape[1]
    index = load_faiss_index(dim)

    index.add(vecs)

    # persist
    chunk_objs.extend(new_objs)
    save_json(chunks_file, chunk_objs)
    save_faiss_index(index)
    return len(new_objs)

def rag_reset():
    # wipe chunks + index
    save_json(current_app.config['CHUNKS_FILE'], [])
    faiss_file = current_app.config['FAISS_FILE']
    if os.path.exists(faiss_file):
        os.remove(faiss_file)

def rag_search(query: str, k: int = None) -> List[Dict]:
    if k is None:
        k = current_app.config['TOP_K']
        
    chunks_file = current_app.config['CHUNKS_FILE']
    chunk_objs = load_json(chunks_file, [])
    if not chunk_objs:
        return []

    # embed query
    qv = embed_texts([query])
    dim = qv.shape[1]
    index = load_faiss_index(dim)

    if index.ntotal == 0:
        return []

    scores, idxs = index.search(qv, k)
    idxs = idxs[0].tolist()
    scores = scores[0].tolist()

    results = []
    for rank, (i, s) in enumerate(zip(idxs, scores), start=1):
        if i < 0 or i >= len(chunk_objs):
            continue
        item = chunk_objs[i].copy()
        item["score"] = float(s)
        item["rank"] = rank
        results.append(item)
    return results

def build_doc_context(retrieved: List[Dict]) -> str:
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
