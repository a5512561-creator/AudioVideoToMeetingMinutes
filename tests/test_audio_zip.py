import zipfile
from pathlib import Path

from script.schemas import SynthesizedMinutes, SynthTopic, SynthAction
from script.audio_zip import build_audio_zip


def _synth():
    return SynthesizedMinutes(
        topics=[SynthTopic(title="議題A", summary="s", decisions=["決議一"],
                           source_timestamps=["00:00:30"])],
        action_items=[SynthAction(task="做 X", owner="小王", due="下週五",
                                  priority="high", source_timestamps=["00:01:10"])],
    )


def test_build_audio_zip_packs_html_and_clips(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    out.mkdir()
    (out / "audio.m4a").write_bytes(b"FAKEAUDIO")

    # Stub the ffmpeg cut: pretend it produced clip files.
    def _fake_cut(audio, starts, duration, out_dir):
        result = {}
        for s in sorted({int(x) for x in starts if x is not None}):
            name = f"clip_{s}.m4a"
            (Path(out_dir) / name).write_bytes(b"CLIPDATA" * 200)  # > 1KB
            result[s] = name
        return result
    monkeypatch.setattr("script.audio_zip.cut_clips", _fake_cut)

    zip_path = build_audio_zip(_synth(), out, pre_seconds=5, duration=10)

    assert zip_path == out / "minutes_audio.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        assert "email_with_audio.html" in names
        assert any(n.startswith("clip_") and n.endswith(".m4a") for n in names)
        html = z.read("email_with_audio.html").decode("utf-8")
        assert "clip_" in html
        assert "data:audio" not in html   # relative refs, not data URLs
        assert "議題A" in html


def test_build_audio_zip_no_audio_returns_none(tmp_path):
    out = tmp_path / "mtg"
    out.mkdir()  # no audio.* present
    assert build_audio_zip(_synth(), out, pre_seconds=5, duration=10) is None
