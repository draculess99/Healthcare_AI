"""RAG Manager — FAISS vector store with keyword-search fallback.

Loads policy and SOP documents from ``data/rag_docs/``, chunks them, and
builds a FAISS index for semantic retrieval.  If ``faiss`` or
``sentence-transformers`` are not installed the module falls back to the
original lightweight keyword search so the app never crashes.

The FAISS index is persisted to ``data/rag_index/`` and rebuilt
automatically when the source documents change.
"""

import os
import hashlib
import json
import re
from typing import List, Dict, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG_DOCS_DIR = os.path.join(_BASE_DIR, "data", "rag_docs")
RAG_INDEX_DIR = os.path.join(_BASE_DIR, "data", "rag_index")
_INDEX_PATH = os.path.join(RAG_INDEX_DIR, "faiss_index.bin")
_CHUNKS_PATH = os.path.join(RAG_INDEX_DIR, "chunks.json")
_HASH_PATH = os.path.join(RAG_INDEX_DIR, "docs_hash.txt")

# Embedding model — small & fast (~80 MB)
_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Chunking parameters
_CHUNK_SIZE = 500       # characters
_CHUNK_OVERLAP = 100    # characters


# ---------------------------------------------------------------------------
# Document loading & chunking
# ---------------------------------------------------------------------------

def _load_documents(docs_dir: str = RAG_DOCS_DIR) -> List[Dict]:
    """Read all .md and .txt files from *docs_dir* and return a flat list."""
    docs: List[Dict] = []
    if not os.path.isdir(docs_dir):
        return docs
    for fname in sorted(os.listdir(docs_dir)):
        if not fname.endswith((".md", ".txt")):
            continue
        fpath = os.path.join(docs_dir, fname)
        with open(fpath, "r", encoding="utf-8") as fh:
            text = fh.read()
        docs.append({"filename": fname, "text": text})
    return docs


def _chunk_text(text: str, filename: str,
                chunk_size: int = _CHUNK_SIZE,
                overlap: int = _CHUNK_OVERLAP) -> List[Dict]:
    """Split *text* into overlapping chunks and return metadata dicts."""
    # Split on section headers first, then re-chunk if sections are too long
    sections = re.split(r'\n(?=##?\s)', text)
    chunks: List[Dict] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= chunk_size:
            chunks.append({
                "text": section,
                "source": filename,
                "chunk_id": len(chunks),
            })
        else:
            # Sliding window within large sections
            start = 0
            while start < len(section):
                end = start + chunk_size
                chunk = section[start:end]
                chunks.append({
                    "text": chunk.strip(),
                    "source": filename,
                    "chunk_id": len(chunks),
                })
                start += chunk_size - overlap
    return chunks


def _docs_hash(docs: List[Dict]) -> str:
    """Return a deterministic hash of all loaded documents."""
    h = hashlib.sha256()
    for d in docs:
        h.update(d["filename"].encode())
        h.update(d["text"].encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# FAISS backend (lazy-loaded to save memory at idle)
# ---------------------------------------------------------------------------

def _try_build_faiss_index(chunks: List[Dict]):
    """Build a FAISS index + embeddings; return (index, model) or None."""
    try:
        import faiss
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        return None

    model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False,
                              convert_to_numpy=True)
    embeddings = embeddings.astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    # Persist to disk
    os.makedirs(RAG_INDEX_DIR, exist_ok=True)
    faiss.write_index(index, _INDEX_PATH)
    with open(_CHUNKS_PATH, "w", encoding="utf-8") as fh:
        json.dump(chunks, fh, ensure_ascii=False)

    return index, model


def _try_load_faiss_index():
    """Load a previously persisted FAISS index; return (index, model) or None."""
    if not os.path.exists(_INDEX_PATH) or not os.path.exists(_CHUNKS_PATH):
        return None
    try:
        import faiss
        from sentence_transformers import SentenceTransformer

        index = faiss.read_index(_INDEX_PATH)
        model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
        with open(_CHUNKS_PATH, "r", encoding="utf-8") as fh:
            chunks = json.load(fh)
        return index, model, chunks
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Keyword fallback (zero extra dependencies)
# ---------------------------------------------------------------------------

def _keyword_search(query: str, chunks: List[Dict], top_k: int = 3) -> List[Dict]:
    """Score chunks by simple word-overlap and return the top *top_k*."""
    query_words = set(query.lower().split())
    scored = []
    for chunk in chunks:
        text_lower = chunk["text"].lower()
        score = sum(1 for w in query_words if w in text_lower)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


# ---------------------------------------------------------------------------
# Public RAGManager class
# ---------------------------------------------------------------------------

class RAGManager:
    """Singleton RAG manager with FAISS vector search + keyword fallback."""

    _instance: Optional["RAGManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    # ---- lazy init --------------------------------------------------------

    def _ensure_initialized(self):
        """Build or load the index on first use (not at import time)."""
        if self._initialized:
            return
        self._initialized = True

        self._chunks: List[Dict] = []
        self._faiss_index = None
        self._faiss_model = None
        self._use_faiss = False

        # Load raw documents
        docs = _load_documents()
        if not docs:
            return

        # Chunk
        for doc in docs:
            self._chunks.extend(_chunk_text(doc["text"], doc["filename"]))

        if os.environ.get("MEDPACK_LOW_MEMORY", "false").lower() in {"1", "true", "yes", "y", "on"}:
            self._use_faiss = False
            return

        current_hash = _docs_hash(docs)

        # Check if we can reuse a cached FAISS index
        cached_hash = ""
        if os.path.exists(_HASH_PATH):
            with open(_HASH_PATH, "r") as fh:
                cached_hash = fh.read().strip()

        if cached_hash == current_hash:
            loaded = _try_load_faiss_index()
            if loaded:
                self._faiss_index, self._faiss_model, self._chunks = loaded
                self._use_faiss = True
                return

        # Build a new index
        result = _try_build_faiss_index(self._chunks)
        if result:
            self._faiss_index, self._faiss_model = result
            self._use_faiss = True
            # Save hash so next load skips rebuild
            os.makedirs(RAG_INDEX_DIR, exist_ok=True)
            with open(_HASH_PATH, "w") as fh:
                fh.write(current_hash)

    # ---- public API -------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict]:
        """Return the top-k most relevant chunks for *query*.

        Each result dict contains ``text``, ``source``, ``chunk_id``, and
        ``score``.
        """
        self._ensure_initialized()
        if not self._chunks:
            return []

        if self._use_faiss:
            return self._faiss_retrieve(query, top_k)
        return self._keyword_retrieve(query, top_k)

    def query_rag(self, query_text: str, n_results: int = 2) -> str:
        """Legacy API — returns a formatted string for the agent committee."""
        results = self.retrieve(query_text, top_k=n_results)
        if not results:
            return "(No relevant policy documents found.)"
        parts = []
        for i, r in enumerate(results, 1):
            source = r.get("source", "unknown")
            parts.append(f"[RAG Document {i} — {source}]: {r['text']}")
        return "\n".join(parts)

    def list_sources(self) -> List[str]:
        """Return a list of all loaded document filenames."""
        self._ensure_initialized()
        return sorted({c["source"] for c in self._chunks})

    def get_stats(self) -> Dict:
        """Return index statistics for the /health or /api/rag endpoint."""
        self._ensure_initialized()
        return {
            "backend": "faiss" if self._use_faiss else "keyword",
            "total_chunks": len(self._chunks),
            "sources": self.list_sources(),
            "embedding_model": _EMBEDDING_MODEL_NAME if self._use_faiss else None,
            "index_path": _INDEX_PATH if self._use_faiss else None,
        }

    # ---- private helpers --------------------------------------------------

    def _faiss_retrieve(self, query: str, top_k: int) -> List[Dict]:
        import numpy as np
        q_embedding = self._faiss_model.encode([query],
                                                convert_to_numpy=True).astype("float32")
        distances, indices = self._faiss_index.search(q_embedding, min(top_k, len(self._chunks)))
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            chunk = dict(self._chunks[idx])
            chunk["score"] = round(float(dist), 4)
            results.append(chunk)
        return results

    def _keyword_retrieve(self, query: str, top_k: int) -> List[Dict]:
        matches = _keyword_search(query, self._chunks, top_k)
        for m in matches:
            m["score"] = 0.0   # keyword search has no numeric distance
        return matches


# Singleton convenience
rag_manager = RAGManager()
