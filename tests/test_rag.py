from __future__ import annotations

import sys
from types import ModuleType

from src.agent.tools import REGISTRY, SEARCH_DOCUMENTS, TOOLS, search_documents
from src.rag.documents import split_into_chunks


def test_split_into_chunks_keeps_overlap() -> None:
    words = [f"word{i}" for i in range(11)]

    chunks = split_into_chunks(" ".join(words), chunk_words=5, overlap_words=2)

    assert chunks == [
        "word0 word1 word2 word3 word4",
        "word3 word4 word5 word6 word7",
        "word6 word7 word8 word9 word10",
    ]


def test_search_documents_tool_is_registered() -> None:
    assert SEARCH_DOCUMENTS in TOOLS
    assert REGISTRY["search_documents"] is search_documents
    assert SEARCH_DOCUMENTS.parameters["required"] == ["query"]


def test_search_documents_returns_source_and_page(monkeypatch) -> None:
    expected = {
        "ok": True,
        "results": [{"text": "The sporting rule.", "source": "sporting.pdf", "page": 12}],
        "row_count": 1,
    }
    fake_retrieval = ModuleType("src.rag.retrieval")
    fake_retrieval.search_documents = lambda query, top_k=5: expected
    monkeypatch.setitem(sys.modules, "src.rag.retrieval", fake_retrieval)

    result = search_documents("How is the race grid set?")

    assert result["ok"] is True
    assert result["results"][0]["source"] == "sporting.pdf"
    assert result["results"][0]["page"] == 12
    assert result["row_count"] == 1


def test_prompt_routes_regulations_to_pdf_search() -> None:
    from src.agent.prompts import build_system_prompt

    prompt = build_system_prompt()

    assert "search_documents" in prompt
    assert "[filename, PDF p. N]" in prompt


def test_prompt_makes_pdf_queries_english() -> None:
    """Retrieval is weak across languages (English PDFs), so the LLM must query in English."""
    from src.agent.prompts import build_system_prompt

    prompt = build_system_prompt()

    assert "always write" in prompt and "`query` in English" in prompt


def test_retrieval_citation_is_ready_to_copy() -> None:
    """The tool hands the LLM the exact citation string, so the format cannot drift."""
    from src.rag.documents import format_citation

    assert format_citation("FIA 2026 - Section B.pdf", 22) == "[FIA 2026 - Section B.pdf, PDF p. 22]"
    from src.agent.prompts import build_system_prompt

    assert "`citation` field" in build_system_prompt()


def test_index_signature_changes_with_the_embedding_model(monkeypatch) -> None:
    """Vectors from different models are not comparable: the signature must reveal a mismatch."""
    from src import config
    from src.rag.documents import CHUNK_OVERLAP_WORDS, CHUNK_WORDS, index_signature

    monkeypatch.setattr(config, "EMBEDDING_MODEL", "model-a")
    first = index_signature()
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "model-b")

    assert first != index_signature()
    assert f"{CHUNK_WORDS}/{CHUNK_OVERLAP_WORDS}" in first
