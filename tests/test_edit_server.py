import json
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


def test_export_outlook_unavailable_still_writes_email(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: False)

    r = handle_export({"synthesized": _synth_dict(), "reviewed": True}, out)

    assert r["ok"] is True
    assert r["outlook_opened"] is False
    assert (out / "email.html").exists()


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
