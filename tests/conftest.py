"""Global test fixtures.

The session-scoped autouse fixture below runs BEFORE any test module is
imported. This ensures that production code's module-level imports such as
`from faster_whisper import WhisperModel` resolve to MagicMocks, preventing
accidental model downloads or real ML inference during unit tests.

Per-test code should still use `patch(...)` to inject test-specific mock
behaviour; this fixture is only a safety net for the common failure mode of
forgetting to patch.
"""
import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture(autouse=True, scope="session")
def _mock_heavy_libs():
    fake_whisper = MagicMock()
    fake_whisper.WhisperModel = MagicMock(name="WhisperModel")
    sys.modules["faster_whisper"] = fake_whisper

    # Mock both the parent namespace and the subpackage; some import
    # resolutions touch the parent first.
    sys.modules["pyannote"] = MagicMock(name="pyannote")
    fake_pyannote_audio = MagicMock()
    fake_pyannote_audio.Pipeline = MagicMock(name="Pipeline")
    sys.modules["pyannote.audio"] = fake_pyannote_audio
    yield
