import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture(autouse=True)
def _mock_heavy_libs(monkeypatch):
    """Prevent any test from accidentally instantiating real ML models."""
    fake_whisper = MagicMock()
    fake_whisper.WhisperModel = MagicMock(name="WhisperModel")
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_whisper)

    fake_pyannote = MagicMock()
    fake_pyannote.Pipeline = MagicMock(name="Pipeline")
    monkeypatch.setitem(sys.modules, "pyannote.audio", fake_pyannote)
