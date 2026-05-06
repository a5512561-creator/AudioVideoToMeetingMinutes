from unittest.mock import MagicMock, patch
from script.transcribe import Segment
from script.diarize import (
    SpeakerSegment,
    TranscribedSegment,
    assign_speakers,
    diarize,
)


def test_assign_speakers_picks_max_overlap_speaker():
    segs = [
        Segment(start=0.0, end=2.0, text="你好"),
        Segment(start=2.0, end=5.0, text="世界 大家好"),
    ]
    speakers = [
        SpeakerSegment(start=0.0, end=2.5, label="SPEAKER_1"),
        SpeakerSegment(start=2.5, end=5.0, label="SPEAKER_2"),
    ]
    out = assign_speakers(segs, speakers)
    assert out == [
        TranscribedSegment(start=0.0, end=2.0, text="你好", speaker="SPEAKER_1"),
        TranscribedSegment(start=2.0, end=5.0, text="世界 大家好", speaker="SPEAKER_2"),
    ]


def test_assign_speakers_handles_no_overlap_with_unknown():
    segs = [Segment(start=0.0, end=1.0, text="x")]
    speakers = [SpeakerSegment(start=10.0, end=11.0, label="SPEAKER_1")]
    out = assign_speakers(segs, speakers)
    assert out[0].speaker == "UNKNOWN"


def test_diarize_invokes_pipeline_with_hf_token():
    fake_pipeline = MagicMock()
    fake_pipeline.return_value = MagicMock(
        itertracks=lambda yield_label: iter([
            (MagicMock(start=0.0, end=2.5), None, "SPEAKER_1"),
            (MagicMock(start=2.5, end=5.0), None, "SPEAKER_2"),
        ])
    )
    with patch("script.diarize.Pipeline.from_pretrained", return_value=fake_pipeline) as ctor:
        out = diarize(
            "audio.wav",
            model="pyannote/speaker-diarization-community-1",
            hf_token="hf_x",
        )
    ctor.assert_called_once_with(
        "pyannote/speaker-diarization-community-1", use_auth_token="hf_x"
    )
    fake_pipeline.assert_called_once_with("audio.wav")
    assert out == [
        SpeakerSegment(start=0.0, end=2.5, label="SPEAKER_1"),
        SpeakerSegment(start=2.5, end=5.0, label="SPEAKER_2"),
    ]
