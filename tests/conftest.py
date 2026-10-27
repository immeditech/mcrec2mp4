import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from mcrec2mp4 import i18n  # noqa: E402


@pytest.fixture(autouse=True)
def german():
    """Tests prüfen die deutschen Texte; einzelne Tests schalten auf Englisch um."""
    i18n.set_lang("de")
    yield
    i18n.set_lang(None)
