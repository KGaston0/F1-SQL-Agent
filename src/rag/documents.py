"""PDF text extraction and page-aware chunking for the local index."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src import config

# 120 words per chunk gave the best retrieval in our benchmark (docs/testing.md): the key sentence of a regulation
# is not diluted by neighboring topics, and each chunk still fits on a single page.
CHUNK_WORDS = 120
CHUNK_OVERLAP_WORDS = 30


def index_signature() -> str:
    """Identifies the settings an index was built with; a query must use the same embedding model."""
    return f"{config.EMBEDDING_MODEL}|{CHUNK_WORDS}/{CHUNK_OVERLAP_WORDS}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def format_citation(source: str, page: int) -> str:
    """Ready-made citation the LLM must copy verbatim, so it never shortens or invents file names."""
    return f"[{source}, PDF p. {page}]"


def clean_page_text(text: str) -> str:
    """Normalize PDF extraction artifacts while keeping words in reading order."""
    text = text.replace("\x00", " ").replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def split_into_chunks(text: str, chunk_words: int = CHUNK_WORDS,
                      overlap_words: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    """Keep each chunk on one PDF page so every answer can cite a precise page."""
    if chunk_words < 1 or not 0 <= overlap_words < chunk_words:
        raise ValueError("overlap_words must be non-negative and smaller than chunk_words")
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def extract_pdf_chunks(path: Path) -> list[tuple[int, int, str]]:
    """Return (PDF page, chunk index, text) tuples; page numbers are one-based."""
    from pypdf import PdfReader

    reader = PdfReader(str(path), strict=False)
    chunks: list[tuple[int, int, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = clean_page_text(page.extract_text() or "")
        chunks.extend((page_number, index, chunk)
                      for index, chunk in enumerate(split_into_chunks(text)))
    if not chunks:
        raise ValueError(f"No extractable text found in {path.name}; scanned PDFs need OCR first.")
    return chunks
