import json
import os
from pathlib import Path

from script.schemas import SynthesizedMinutes, SynthTopic, SynthAction
from script.edit_server import handle_export, load_data


def _synth_dict(**over):
    s = SynthesizedMinutes(
        topics=[SynthTopic(title="議題A", summary="討論內容", decisions=["決議一"])],
        action_items=[SynthAction(task="做 X", owner="小王", due="下週五", priority="high")],
    )
    d = json.loads(s.model_dump_json())
    d.update(over)
    return d


def test_export_writes_outputs_and_opens_outlook(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    seen = {}
    monkeypatch.setattr("script.edit_server.open_draft",
                        lambda subj, html: seen.update(subj=subj, html=html) or True)

    r = handle_export({"synthesized": _synth_dict(), "reviewed": True}, out)

    assert r["ok"] is True
    assert r["outlook_opened"] is True
    assert (out / "email.html").exists()
    assert (out / "intermediate" / "synthesized.json").exists()
    assert seen["subj"] == "mtg"
    assert "議題A" in seen["html"]


def test_export_blocked_when_layer1_fails(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: True)
    bad = _synth_dict()
    bad["action_items"][0]["owner"] = ""

    r = handle_export({"synthesized": bad, "reviewed": True}, out)

    assert r["ok"] is False
    assert r["reason"] == "audit_failed"
    assert any(f["key"] == "action_owner_present" for f in r["failing"])
    assert not (out / "email.html").exists()


def test_export_blocked_when_not_reviewed(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: True)

    r = handle_export({"synthesized": _synth_dict(), "reviewed": False}, out)

    assert r["ok"] is False
    assert r["reason"] == "not_reviewed"
    assert not (out / "email.html").exists()
    assert not (out / "intermediate" / "synthesized.json").exists()


def test_export_rejects_non_dict_payload(tmp_path):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    r = handle_export([], out)
    assert r["ok"] is False
    assert r["reason"] == "invalid_payload"
    assert not (out / "email.html").exists()


def test_export_outlook_unavailable_still_writes_email(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: False)

    r = handle_export({"synthesized": _synth_dict(), "reviewed": True}, out)

    assert r["ok"] is True
    assert r["outlook_opened"] is False
    assert (out / "email.html").exists()


def test_render_edit_page_embeds_data_and_controls(tmp_path):
    from script.edit_server import render_edit_page
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="議題A", summary="s")]).model_dump_json(),
        encoding="utf-8")

    html = render_edit_page(out)

    assert "window.DATA" in html
    assert "議題A" in html
    assert 'id="exportbtn"' in html
    assert 'id="reviewed"' in html


def test_load_data_returns_synth_and_audit(tmp_path):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="議題A", summary="s")]).model_dump_json(),
        encoding="utf-8")
    data = load_data(out)
    assert data["synthesized"]["topics"][0]["title"] == "議題A"
    assert data["audit"]["reviewed"] is False
    assert data["audit"]["mechanical"] == []


def test_server_serves_page_and_handles_export(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from script.edit_server import build_server

    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(
            topics=[SynthTopic(title="議題A", summary="s", decisions=["決議一"])]
        ).model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: False)

    httpd = build_server(out)
    assert httpd.server_address[0] == "127.0.0.1"   # localhost-only
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
        assert "議題A" in page and 'id="exportbtn"' in page

        body = json.dumps({
            "synthesized": {
                "topics": [{"title": "議題A", "summary": "s", "decisions": ["決議一"]}],
                "action_items": [],
            },
            "reviewed": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/export", data=body,
            headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
        assert res["ok"] is True
        assert (out / "email.html").exists()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_export_failure_returns_422(tmp_path, monkeypatch):
    import threading
    import urllib.request
    import urllib.error
    from script.edit_server import build_server

    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes().model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: True)

    httpd = build_server(out)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        body = json.dumps({
            "synthesized": {"topics": [], "action_items": [
                {"task": "x", "owner": "", "due": "", "priority": "high"}]},
            "reviewed": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/export", data=body,
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            raised = None
        except urllib.error.HTTPError as e:
            raised = e
        assert raised is not None and raised.code == 422
        payload = json.loads(raised.read().decode("utf-8"))
        assert payload["reason"] == "audit_failed"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_registry_round_trip(tmp_path):
    from script.edit_server import read_registry, write_registry, clear_registry
    out = tmp_path / "mtg"
    out.mkdir()
    assert read_registry(out) is None                 # absent -> None
    write_registry(out, pid=4242, port=54321)
    reg = read_registry(out)
    assert reg == {"pid": 4242, "port": 54321, "name": "mtg"}
    assert (out / ".edit-server.json").exists()
    clear_registry(out)
    assert read_registry(out) is None                 # cleared -> None
    clear_registry(out)                               # idempotent, no raise


def test_registry_corrupt_reads_as_none(tmp_path):
    from script.edit_server import read_registry
    out = tmp_path / "mtg"
    out.mkdir()
    (out / ".edit-server.json").write_text("{not json", encoding="utf-8")
    assert read_registry(out) is None


def test_ping_returns_app_and_meeting_marker(tmp_path):
    import threading
    import urllib.request
    from script.edit_server import build_server

    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="議題A", summary="s")]).model_dump_json(),
        encoding="utf-8")

    httpd = build_server(out)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        body = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/ping", timeout=2).read().decode("utf-8")
        data = json.loads(body)
        assert data == {"app": "minutes-edit", "name": "mtg"}
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_existing_live_url_returns_url_on_matching_ping(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    edit_server.write_registry(out, pid=1, port=6001)
    monkeypatch.setattr(edit_server, "_ping_ok",
                        lambda port, name: port == 6001 and name == "mtg")
    assert edit_server.existing_live_url(out) == "http://127.0.0.1:6001/"


def test_existing_live_url_none_and_clears_when_dead(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    edit_server.write_registry(out, pid=1, port=6002)
    monkeypatch.setattr(edit_server, "_ping_ok", lambda port, name: False)  # dead / wrong
    assert edit_server.existing_live_url(out) is None
    assert edit_server.read_registry(out) is None            # stale registry cleared


def test_serve_reuses_live_server_without_binding(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    monkeypatch.setattr(edit_server, "existing_live_url",
                        lambda o: "http://127.0.0.1:7777/")
    opened = {}
    monkeypatch.setattr(edit_server.webbrowser, "open",
                        lambda u: opened.update(url=u))
    # If serve tried to bind a real server it would call build_server; fail loudly.
    monkeypatch.setattr(edit_server, "build_server",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not bind")))

    edit_server.serve(out, open_browser=True)          # returns immediately

    assert opened["url"] == "http://127.0.0.1:7777/"


def test_serve_fresh_writes_registry_during_serve_and_clears_after(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    monkeypatch.setattr(edit_server, "existing_live_url", lambda o: None)
    monkeypatch.setattr(edit_server.webbrowser, "open", lambda u: None)

    seen = {}

    class _FakeHttpd:
        server_address = ("127.0.0.1", 8123)
        def serve_forever(self):
            # registry must exist *while* the server is running
            seen["during"] = edit_server.read_registry(out)
        def server_close(self):
            seen["closed"] = True

    monkeypatch.setattr(edit_server, "build_server", lambda o, port=0: _FakeHttpd())

    edit_server.serve(out, open_browser=False)

    assert seen["during"] == {"pid": os.getpid(), "port": 8123, "name": "mtg"}
    assert seen["closed"] is True
    assert edit_server.read_registry(out) is None      # cleared in finally


def test_existing_live_url_none_when_no_registry(tmp_path):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    assert edit_server.existing_live_url(out) is None


def test_ping_ok_false_on_connection_error(monkeypatch):
    from script import edit_server
    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert edit_server._ping_ok(59999, "mtg") is False
