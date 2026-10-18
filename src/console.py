"""Sorties Unicode du programme, y compris quand Windows les redirige."""
import sys


def configure_console():
    # Ne pas remplacer les flux des IDE/tests. TextIOWrapper permet de choisir
    # l'encodage sans changer stdout/stderr ou perdre les tampons en cours.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            reconfigure(encoding='utf-8', errors='backslashreplace', write_through=True)
