import subprocess
from unittest.mock import patch
from script.diarize import SpeakerSegment
from script.sample_extractor import extract_speaker_samples


def _seg(s, e, label):
    return SpeakerSegment(start=s, end=e, label=label)


def test_no_speakers_returns_empty(tmp_path):
    assert extract_speaker_samples(
        audio_path=str(tmp_path / "a.wav"),
        speakers=[],
        out_dir=str(tmp_path / "samples"),
    ) == []


def test_extracts_one_per_label_using_longest_segment(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    speakers = [
        _seg(0.0, 2.0, "SPEAKER_00"),
        _seg(10.0, 30.5, "SPEAKER_00"),    # longest for 00
        _seg(50.0, 51.0, "SPEAKER_00"),
        _seg(5.0, 25.0, "SPEAKER_01"),
    ]
    with patch("script.sample_extractor._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.sample_extractor.subprocess.run") as run:
        run.return_value.returncode = 0
        out = extract_speaker_samples(
            audio_path=str(audio),
            speakers=speakers,
            out_dir=str(tmp_path / "samples"),
            target_duration_sec=10.0,
        )

    assert len(out) == 2
    # Two ffmpeg calls, sorted by label
    assert run.call_count == 2
    cmd0 = run.call_args_list[0][0][0]
    cmd1 = run.call_args_list[1][0][0]
    # SPEAKER_00 longest is (10.0, 30.5) → 20.5s, dur >= 10 → start=10.0
    assert "-ss" in cmd0 and "10.00" in cmd0
    assert cmd0[-1].endswith("SPEAKER_00.mp3")
    # SPEAKER_01 longest is (5.0, 25.0) → 20s → start=5.0
    assert "5.00" in cmd1
    assert cmd1[-1].endswith("SPEAKER_01.mp3")


def test_short_segment_is_centred_to_target_duration(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    # only segment is 4 seconds long → need 3 sec extra each side → start = 50 - 3 = 47
    speakers = [_seg(50.0, 54.0, "SPEAKER_00")]
    with patch("script.sample_extractor._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.sample_extractor.subprocess.run") as run:
        run.return_value.returncode = 0
        extract_speaker_samples(
            audio_path=str(audio),
            speakers=speakers,
            out_dir=str(tmp_path / "samples"),
            target_duration_sec=10.0,
        )
    cmd = run.call_args[0][0]
    assert "-ss" in cmd and "47.00" in cmd
    assert "-t" in cmd and "10.00" in cmd


def test_short_segment_does_not_clip_below_zero(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    # 3-sec segment starting at t=1s; centring would ask -2.5s → must clamp to 0
    speakers = [_seg(1.0, 4.0, "SPEAKER_00")]
    with patch("script.sample_extractor._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.sample_extractor.subprocess.run") as run:
        run.return_value.returncode = 0
        extract_speaker_samples(
            audio_path=str(audio),
            speakers=speakers,
            out_dir=str(tmp_path / "samples"),
        )
    cmd = run.call_args[0][0]
    assert "0.00" in cmd  # clamped


def test_returns_empty_when_ffmpeg_missing(tmp_path):
    with patch("script.sample_extractor._find_ffmpeg", return_value=None):
        out = extract_speaker_samples(
            audio_path="x.wav",
            speakers=[_seg(0, 10, "SPEAKER_00")],
            out_dir=str(tmp_path / "samples"),
        )
    assert out == []


def test_skips_failed_ffmpeg_runs(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    speakers = [
        _seg(0, 20, "SPEAKER_00"),
        _seg(0, 20, "SPEAKER_01"),
    ]
    with patch("script.sample_extractor._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.sample_extractor.subprocess.run") as run:
        # First succeeds, second fails
        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        bad = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        run.side_effect = [ok, bad]
        out = extract_speaker_samples(
            audio_path=str(audio),
            speakers=speakers,
            out_dir=str(tmp_path / "samples"),
        )
    assert len(out) == 1
    assert out[0].endswith("SPEAKER_00.mp3")


def test_uses_libmp3lame_with_q4_quality(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    speakers = [_seg(0, 12, "SPEAKER_00")]
    with patch("script.sample_extractor._find_ffmpeg", return_value="ffmpeg"), \
         patch("script.sample_extractor.subprocess.run") as run:
        run.return_value.returncode = 0
        extract_speaker_samples(
            audio_path=str(audio),
            speakers=speakers,
            out_dir=str(tmp_path / "samples"),
        )
    cmd = run.call_args[0][0]
    assert "-c:a" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "libmp3lame"
    assert "-q:a" in cmd
    assert cmd[cmd.index("-q:a") + 1] == "4"
    assert "-nostdin" in cmd  # same anti-truncation guard as media.py
