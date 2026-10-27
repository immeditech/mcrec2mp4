"""Sprache der Ausgaben: Deutsch auf deutschsprachigen Systemen, sonst Englisch.

Texte folgen der Systemsprache (LANGUAGE/LC_ALL/LC_MESSAGES/LANG), das Datumsformat dem
Datumsformat (LC_ALL/LC_TIME/LANG). Beides überschreibt MCREC2MP4_LANG=de|en.
"""
import locale
import os
import sys

_lang = None
_time_lang = None


def _detect(env_vars=("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"), win_call="GetUserDefaultUILanguage"):
    env = os.environ.get("MCREC2MP4_LANG")
    if env:
        return "de" if env.lower().startswith("de") else "en"
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            return "de" if val.lower().startswith("de") else "en"
    if sys.platform == "win32":
        try:
            import ctypes
            # Primärsprache 0x07 = Deutsch (de-DE, de-CH, de-AT, …)
            return "de" if getattr(ctypes.windll.kernel32, win_call)() & 0x3FF == 0x07 else "en"
        except Exception:
            pass
    try:
        loc = locale.getlocale()[0] or ""
    except Exception:
        loc = ""
    return "de" if loc.lower().startswith(("de", "german")) else "en"


def lang():
    global _lang
    if _lang is None:
        _lang = _detect()
    return _lang


def time_lang():
    """Sprache für Datumsformate (kann von der Textsprache abweichen, z. B. LANG=en_US + LC_TIME=de_CH)."""
    global _time_lang
    if _time_lang is None:
        _time_lang = _detect(("LC_ALL", "LC_TIME", "LANG"), "GetUserDefaultLCID")
    return _time_lang


def set_lang(value):
    """Für Tests: Sprache fest setzen (None = neu erkennen)."""
    global _lang, _time_lang
    _lang = _time_lang = value


def date_fmt(seconds=True):
    if time_lang() == "de":
        return "%d.%m.%Y %H:%M:%S" if seconds else "%d.%m.%Y %H:%M"
    return "%Y-%m-%d %H:%M:%S" if seconds else "%Y-%m-%d %H:%M"


def t(de, en):
    return de if lang() == "de" else en
