# 03 – Decisiones técnicas

| Decisión | Elegido | Motivo |
|---|---|---|
| Dominio | Fórmula 1 (datos reales 1950-presente, API Jolpica) | Datos abiertos y verificables, 11 tablas, +26k resultados |
| BD | SQLite, carga programática con caché local reanudable | Archivo único, reproducible, sin servidor; modo offline |
| LLM | Gemini (tier gratuito/académico) | Acceso disponible, function calling nativo |
| Agente | Tool-use nativo, sin framework | Simple de defender; el LLM decide la fuente |
| Vectores | ChromaDB local | Sin servidor, persistente en carpeta |
| Embeddings | sentence-transformers multilingüe (local) | Gratis, soporta español, sin depender de cuota |
| UI | Streamlit chat | Demo y ejecución sencillas |

> TODO: alternativas descartadas y trade-offs, a completar al implementar.
