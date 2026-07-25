# Nancy AI Models Reference

This page describes the AI model surface in Nancy.

## Backends
Nancy supports multiple LLM backends with fallback behavior. Backends are configured via environment variables and discovered at runtime.

Example env-backed options:
- OpenAI
- Anthropic
- Groq
- OpenRouter
- Nous Portal–style custom endpoint
- Ollama local fallback

## Frontend model selectors
The AI Core and Models panels read state from backend status/model endpoints. Use the UI to inspect current primary model and backends when possible.
