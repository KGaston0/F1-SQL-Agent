# TP Integrador – Agente SQL + RAG

Asistente que responde preguntas en lenguaje natural (castellano/inglés) consultando una base relacional (SQLite, datos históricos reales de Fórmula 1) y PDFs (RAG), decidiendo por sí mismo qué fuente usar. Incluye una UI de chat básica en Streamlit.

> Estado: **estructura y documentación iniciales. El código aún no está implementado.**

## Stack
Python 3.11+ · SQLite · Gemini (function calling, SDK `google-genai`) · ChromaDB + sentence-transformers (embeddings locales) · Streamlit.

## Instalación y ejecución (a completar al implementar)
```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # completar GEMINI_API_KEY
python scripts/init_db.py     # descarga datos reales de F1 (API Jolpica) y crea la BD (~10-20 min la 1a vez)
python scripts/ingest_pdfs.py # indexa los PDFs en Chroma
streamlit run src/ui/app.py
```

## Estructura
- `data/` BD (`db/`), PDFs (`pdfs/`), índice vectorial (`vectorstore/`, regenerable)
- `src/database` esquema y datos sintéticos · `src/rag` ingesta y recuperación · `src/agent` loop del agente y herramientas · `src/ui` chat Streamlit
- `scripts/` utilidades de arranque · `tests/` pruebas
- `docs/` documentación técnica, informe y guion del coloquio

## Checklist de criterios de aprobación
- [ ] BD con ≥5 tablas y >15 registros por tabla
- [ ] Preguntas en lenguaje natural respondidas con la BD
- [ ] RAG sobre ≥2 PDFs
- [ ] Código documentado y reproducible
- [ ] Informe ≤10 páginas (`docs/informe/`)
- [ ] Coloquio preparado (`docs/coloquio.md`)
- [ ] UI básica (único punto opcional tomado)

Entrega: 16/10/2026 23:59 (GMT-3). Coloquios: 23/10 y 30/10.
