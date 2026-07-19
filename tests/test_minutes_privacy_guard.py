import json
from pathlib import Path

from hooks.minutes_privacy_guard import should_block, find_lock, _resolve


LOCK = {"protected": ["/proj/mtg/mtg.vtt", "/proj/mtg/mtg.m4a"]}


def test_blocks_read_of_protected_transcript():
    blocked, reason = should_block("Read", {"file_path": "/proj/mtg/mtg.vtt"}, LOCK)
    assert blocked is True
    assert "company" in reason.lower() or "公司" in reason


def test_blocks_bash_command_touching_protected_audio():
    blocked, _ = should_block(
        "Bash", {"command": "cat /proj/mtg/mtg.m4a | base64"}, LOCK)
    assert blocked is True


def test_allows_unrelated_read():
    blocked, _ = should_block("Read", {"file_path": "/proj/other/readme.md"}, LOCK)
    assert blocked is False


def test_allows_everything_when_no_lock():
    blocked, _ = should_block("Read", {"file_path": "/proj/mtg/mtg.vtt"}, None)
    assert blocked is False
    blocked, _ = should_block("Read", {"file_path": "/proj/mtg/mtg.vtt"}, {"protected": []})
    assert blocked is False


def test_grep_and_glob_over_protected_path_blocked():
    blocked, _ = should_block("Grep", {"path": "/proj/mtg/mtg.vtt"}, LOCK)
    assert blocked is True
    blocked_glob, _ = should_block("Glob", {"path": "/proj/mtg/mtg.vtt"}, LOCK)
    assert blocked_glob is True


def test_path_normalisation_matches_mixed_separators():
    lock = {"protected": ["C:/proj/mtg/mtg.vtt"]}
    blocked, _ = should_block("Read", {"file_path": "C:\\proj\\mtg\\mtg.vtt"}, lock)
    assert blocked is True


def test_find_lock_walks_up_from_target_dir(tmp_path):
    mtg = tmp_path / "meetings" / "m1"
    mtg.mkdir(parents=True)
    (mtg / ".minutes-company-lock.json").write_text(
        json.dumps({"protected": ["m1.vtt"]}), encoding="utf-8")
    lock, lock_dir = find_lock(str(mtg / "sub"))  # start below the lock dir
    assert lock == {"protected": ["m1.vtt"]}
    assert Path(lock_dir) == mtg.resolve()


def test_find_lock_absent_returns_none(tmp_path):
    lock, lock_dir = find_lock(str(tmp_path))
    assert lock is None and lock_dir is None


def test_find_lock_corrupt_fails_closed(tmp_path):
    (tmp_path / ".minutes-company-lock.json").write_text("{bad json", encoding="utf-8")
    lock, lock_dir = find_lock(str(tmp_path))
    assert lock == {"protected": ["*"]}


def test_relative_protected_path_resolves_against_lock_dir(tmp_path):
    lock_dir = tmp_path / "mtg"
    lock_dir.mkdir()
    lock = {"protected": ["m.vtt"]}
    target = str(lock_dir / "m.vtt")
    blocked, _ = should_block("Read", {"file_path": target}, lock, str(lock_dir))
    assert blocked is True


def test_wildcard_lock_blocks_reads():
    blocked, reason = should_block("Read", {"file_path": "/anything"}, {"protected": ["*"]})
    assert blocked is True
    blocked2, _ = should_block("Grep", {"path": "/x"}, {"protected": ["*"]})
    assert blocked2 is True
    blocked3, _ = should_block("Bash", {"command": "cat /x"}, {"protected": ["*"]})
    assert blocked3 is True


def test_dotdot_path_cannot_bypass_block():
    lock = {"protected": ["/proj/mtg/mtg.vtt"]}
    blocked, _ = should_block("Read", {"file_path": "/proj/mtg/z/../mtg.vtt"}, lock)
    assert blocked is True


def test_dotdot_via_grep_path_blocked():
    lock = {"protected": ["/proj/mtg/mtg.vtt"]}
    blocked, _ = should_block("Grep", {"path": "/proj/mtg/sub/../mtg.vtt"}, lock)
    assert blocked is True


import io
import json as _json
from hooks import minutes_privacy_guard as _guard


def test_main_blocks_protected_read_via_stdin(tmp_path, monkeypatch, capsys):
    (tmp_path / "m.vtt").write_text("secret", encoding="utf-8")
    (tmp_path / ".minutes-company-lock.json").write_text(
        _json.dumps({"protected": [str(tmp_path / "m.vtt")]}), encoding="utf-8")
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "m.vtt")}}
    monkeypatch.setattr("sys.stdin", io.StringIO(_json.dumps(payload)))
    rc = _guard.main()
    assert rc == 2
    assert "隱私" in capsys.readouterr().err


def test_main_allows_when_no_lock(tmp_path, monkeypatch):
    payload = {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "x.md")}}
    monkeypatch.setattr("sys.stdin", io.StringIO(_json.dumps(payload)))
    assert _guard.main() == 0


def test_main_allows_unparseable_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert _guard.main() == 0
