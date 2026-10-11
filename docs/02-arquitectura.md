# 02 – Arquitectura del agente

> TODO al implementar.

## Flujo
Pregunta → Gemini (con 2 herramientas) → `consultar_sql` y/o `buscar_documentos` → respuesta final.

## Contenido a completar
- Diagrama (mermaid) de componentes y de secuencia
- Criterio de decisión SQL vs RAG vs ambas (prompt de sistema)
- Salvaguardas: solo SELECT, límite de filas, timeout, esquema inyectado en el prompt
- Pipeline RAG: PDF → chunks → embeddings locales → Chroma → top-k
- Manejo de errores y cuota del tier gratuito de Gemini (reintentos con backoff)
