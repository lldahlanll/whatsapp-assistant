app/ai/
├── __init__.py          # Public API exports
├── circuit_breaker.py   # Variable-duration breaker
├── client.py            # MultiProviderClient (singleton)
├── models.py            # Tier definitions & routes
├── postprocess.py       # Strip <think>, normalize output
├── prompts.py           # Layered prompt system
├── providers.py         # Groq/Gemini/OpenRouter + error classify
└── router.py            # classify → build prompt → fallback chain