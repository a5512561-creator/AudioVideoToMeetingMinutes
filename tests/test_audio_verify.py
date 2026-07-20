import zipfile
from pathlib import Path

from script.audio_verify import prezip_check


def _make_zip(tmp_path, html, clip_names, clip_bytes=b"X" * 2048):
    z = tmp_path / "minutes_audio.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("email_with_audio.html", html)
        for n in clip_names:
            zf.writestr(n, clip_bytes)
    return z


def test_prezip_check_ok(tmp_path):
    html = '<audio></audio><script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    r = prezip_check(z)
    assert r["ok"] is True
    assert r["clip_count"] == 1


def test_prezip_check_flags_broken_link(tmp_path):
    # HTML references clip_99 but it is not in the zip
    html = '<script>var CLIPS={"99":"clip_99.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    r = prezip_check(z)
    assert r["ok"] is False
    assert "clip_99.m4a" in r["missing"]


def test_prezip_check_flags_tiny_clip(tmp_path):
    html = '<script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"], clip_bytes=b"tiny")
    r = prezip_check(z)
    assert r["ok"] is False
    assert "clip_30.m4a" in r["too_small"]


def test_verify_and_cleanup_all_pass(tmp_path, monkeypatch):
    from script.audio_verify import verify_zip
    html = '<script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    # stub ffprobe: every clip reports 10.0s of audio
    monkeypatch.setattr("script.audio_verify._probe_duration", lambda p: 10.0)

    r = verify_zip(z, run_browser=False)

    assert r["ok"] is True
    assert r["audible"] == ["clip_30.m4a"]
    # temp unzip dir removed on success
    assert r["temp_dir"] is None or not Path(r["temp_dir"]).exists()


def test_verify_keeps_temp_on_silent_clip(tmp_path, monkeypatch):
    from script.audio_verify import verify_zip
    html = '<script>var CLIPS={"30":"clip_30.m4a"};</script>'
    z = _make_zip(tmp_path, html, ["clip_30.m4a"])
    monkeypatch.setattr("script.audio_verify._probe_duration", lambda p: 0.0)  # silent/broken

    r = verify_zip(z, run_browser=False)

    assert r["ok"] is False
    assert "clip_30.m4a" in r["silent"]
    # temp kept for inspection on failure
    assert r["temp_dir"] is not None and Path(r["temp_dir"]).exists()
