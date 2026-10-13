"""Persistent Chroma index and local semantic retrieval for PDF chunks."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from src import config
from src.rag.documents import format_citation, index_signature

COLLECTION_NAME = "f1_regulations"
MAX_TOP_K = 4


@lru_cache(maxsize=1)
def _collection():
    """Reuse the local collection for all tool calls in a process."""
    client = chromadb.PersistentClient(path=str(config.VECTORSTORE_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


@lru_cache(maxsize=1)
def _index_matches_settings() -> tuple[bool, str]:
    """Compare the settings stored in the index with the current ones (vectors from different models are not comparable)."""
    sample = _collection().get(limit=1, include=["metadatas"])["metadatas"]
    built_with = (sample[0] or {}).get("index_config", "unknown") if sample else "unknown"
    return built_with == index_signature(), built_with


@lru_cache(maxsize=1)
def _embedding_model() -> SentenceTransformer:
    # Indexing downloads the model once; normal queries should stay fully local.
    return SentenceTransformer(config.EMBEDDING_MODEL, local_files_only=True)


def search_documents(query: str, top_k: int = 2) -> dict[str, Any]:
    """Find relevant PDF excerpts with source and page metadata for grounded answers."""
    query = " ".join(query.split())
    if not query:
        return {"ok": False, "error": "Missing 'query' argument.", "results": []}

    collection = _collection()
    count = collection.count()
    if not count:
        return {
            "ok": False,
            "error": "The PDF index is empty. Run `python scripts/index_pdfs.py` first.",
            "results": [],
        }

    matches, built_with = _index_matches_settings()
    if not matches:
        return {
            "ok": False,
            "error": (f"The PDF index was built with '{built_with}' but the current settings are "
                      f"'{index_signature()}'. Run `python scripts/index_pdfs.py --rebuild`."),
            "results": [],
        }

    model = _embedding_model()
    encode_query = getattr(model, "encode_query", model.encode)
    embedding = encode_query(query, normalize_embeddings=True).tolist()
    hits = collection.query(
        query_embeddings=[embedding],
        n_results=min(max(1, top_k), MAX_TOP_K, count),
        include=["documents", "metadatas", "distances"],
    )

    documents = hits["documents"][0]
    metadatas = hits["metadatas"][0]
    distances = hits["distances"][0]
    results = [
        {
            "text": text,
            "source": metadata["source"],
            "page": metadata["page"],
            "citation": format_citation(metadata["source"], metadata["page"]),
            "similarity": round(1 - distance, 3),
        }
        for text, metadata, distance in zip(documents, metadatas, distances)
        if text and metadata
    ]
    return {"ok": True, "results": results, "row_count": len(results)}
