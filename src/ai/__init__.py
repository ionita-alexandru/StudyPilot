"""Accès centralisé aux modèles utilisés par StudyPilot."""

from .client import AIUnavailableError, chat, chat_json, chat_text

__all__ = ["AIUnavailableError", "chat", "chat_json", "chat_text"]
