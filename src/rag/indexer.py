"""Build or incrementally refresh the persistent index from data/pdfs."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import truststore

truststore.inject_into_ssl()

import chromadb
from sentence_transformers import SentenceTransformer

from src import config
from src.rag.documents import extract_pdf_chunks, file_sha256
from src.rag.retrieval import COLLECTION_NAME


def _chunk_id(source: str, page: int, chunk_index: int, text: str) -> str:
    raw = f"{source}\0{page}\0{chunk_index}\0{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def index_pdfs(pdf_dir: Path | None = None, rebuild: bool = False) -> dict[str, Any]:
    """Index new or changed PDFs and remove entries for files no longer present."""
    directory = pdf_dir or config.PDF_DIR
    paths = sorted(directory.glob("*.pdf")) if directory.exists() else []
    if not paths:
        raise FileNotFoundError(f"No PDF files found in {directory}")

    client = chromadb.PersistentClient(path=str(config.VECTORSTORE_DIR))
    if rebuild:
        existing_names = {
            item.name if hasattr(item, "name") else str(item)
            for item in client.list_collections()
        }
        if COLLECTION_NAME in existing_names:
            client.delete_collection(name=COLLECTION_NAME)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    existing = collection.get(include=["metadatas"])
    existing_by_source: dict[str, list[dict[str, Any]]] = {}
    for metadata in existing.get("metadatas") or []:
        if metadata:
            existing_by_source.setdefault(metadata["source"], []).append(metadata)

    model: SentenceTransformer | None = None
    indexed: list[str] = []
    skipped: list[str] = []
    current_sources = {path.name for path in paths}

    for path in paths:
        source_hash = file_sha256(path)
        previous = existing_by_source.get(path.name, [])
        if previous and all(item.get("source_hash") == source_hash for item in previous):
            skipped.append(path.name)
            continue

        page_chunks = extract_pdf_chunks(path)
        if model is None:
            model = SentenceTransformer(config.EMBEDDING_MODEL)
        texts = [text for _, _, text in page_chunks]
        encode_documents = getattr(model, "encode_document", model.encode)
        vectors = encode_documents(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=True,
        ).tolist()
        ids = [_chunk_id(path.name, page, index, text)
               for page, index, text in page_chunks]
        metadatas = [
            {"source": path.name, "page": page, "chunk": index, "source_hash": source_hash}
            for page, index, _ in page_chunks
        ]

        if previous:
            collection.delete(where={"source": path.name})
        for start in range(0, len(ids), 500):
            end = start + 500
            collection.add(
                ids=ids[start:end],
                documents=texts[start:end],
                embeddings=vectors[start:end],
                metadatas=metadatas[start:end],
            )
        indexed.append(f"{path.name} ({len(texts)} chunks)")

    stale_ids = [
        chunk_id
        for chunk_id, metadata in zip(existing.get("ids") or [], existing.get("metadatas") or [])
        if metadata and metadata.get("source") not in current_sources
    ]
    if stale_ids:
        collection.delete(ids=stale_ids)

    return {
        "indexed": indexed,
        "skipped": skipped,
        "removed_chunks": len(stale_ids),
        "total_chunks": collection.count(),
        "index_path": str(config.VECTORSTORE_DIR),
    }
