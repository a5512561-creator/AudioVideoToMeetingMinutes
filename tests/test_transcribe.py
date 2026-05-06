from unittest.mock import MagicMock, patch
from script.transcribe import transcribe, Segment


def test_transcribe_returns_segments_and_calls_whisper_with_config():
    fake_seg1 = MagicMock(start=0.0, end=2.5, text="你好")
    fake_seg2 = MagicMock(start=2.5, end=5.0, text="世界")
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_seg1, fake_seg2], MagicMock())

    with patch("script.transcribe.WhisperModel", return_value=fake_model) as ctor:
        segs = transcribe(
            "audio.wav",
            model="large-v3",
            device="cpu",
            compute_type="int8",
            language="zh",
            initial_prompt="prompt",
            vad_filter=True,
        )

    ctor.assert_called_once_with("large-v3", device="cpu", compute_type="int8")
    fake_model.transcribe.assert_called_once_with(
        "audio.wav",
        language="zh",
        initial_prompt="prompt",
        vad_filter=True,
    )
    assert segs == [
        Segment(start=0.0, end=2.5, text="你好"),
        Segment(start=2.5, end=5.0, text="世界"),
    ]
