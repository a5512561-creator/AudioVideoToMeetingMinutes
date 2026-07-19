from hooks.minutes_privacy_guard import should_block


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


def test_path_normalisation_matches_mixed_separators():
    lock = {"protected": ["C:/proj/mtg/mtg.vtt"]}
    blocked, _ = should_block("Read", {"file_path": "C:\\proj\\mtg\\mtg.vtt"}, lock)
    assert blocked is True
