"""Adaptateur Gemini Flash : transport Google partagé, aucun repli automatique."""
from src.ai.gemma import gemma_chat

# Offre gratuite publiée par Google le 19 octobre 2026 ; quotas propres au projet.
MODELS = {'gemini-3.8-flash'}


def gemini_chat(*, messages, model, format=None, options=None, think=None):
    # Flash refuse MINIMAL, utilisé par défaut pour Gemma sur le transport commun.
    return gemma_chat(
        messages=messages, model=model, format=format, options=options, think=think,
        _allowed_models=MODELS,
        _thinking_level='high' if think in (True, 'high') else 'low',
    )
