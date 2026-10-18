"""File d'appels dans le serveur : priorité aux questions entre deux lots d'import."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import threading
import time

_priority = ContextVar('study_priority', default=0)
_budget = ContextVar('study_budget', default=None)
_condition = threading.Condition()
_active = False
_interactive_waiting = 0


@contextmanager
def interactive():
    token = _priority.set(1)
    try: yield
    finally: _priority.reset(token)


@contextmanager
def budget_scope(budget):
    token = _budget.set(budget)
    try: yield
    finally: _budget.reset(token)


def request_attempt(input_tokens=0, output_tokens=0):
    budget = _budget.get()
    if budget is None:
        return
    from src.ai.client import AIUsageLimitError
    tokens = max(0, input_tokens or 0) + max(0, output_tokens or 0)
    if (time.monotonic() >= budget.deadline or budget.network_requests >= budget.max_calls * 8
            or budget.reserved_tokens + tokens > budget.max_calls * 14000):
        raise AIUsageLimitError('Budget réseau/jetons atteint ; reprise possible depuis les lots enregistrés.')
    budget.network_requests += 1
    budget.reserved_tokens += tokens


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        global _active, _interactive_waiting
        priority = _priority.get()
        with _condition:
            if priority: _interactive_waiting += 1
            try:
                while _active or (not priority and _interactive_waiting):
                    _condition.wait(timeout=1)
                _active = True
            finally:
                if priority: _interactive_waiting -= 1
        try:
            return function(*args, **kwargs)
        finally:
            with _condition:
                _active = False
                _condition.notify_all()
    return wrapped
