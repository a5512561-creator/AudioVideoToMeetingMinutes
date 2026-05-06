from unittest.mock import MagicMock
from script.schemas import CorrectionResult, CorrectionDiff
from script.transcript_corrector import correct_transcript


def test_correct_transcript_chunks_and_concatenates(tmp_path):
    src = tmp_path / "t.md"
    src.write_text(
        "[00:00:01] 肖王您好。\n[00:00:05] 菲尼克斯產品。\n",
        encoding="utf-8",
    )
    glossary_path = tmp_path / "glossary.md"
    glossary_path.write_text("- 小王\n- Phoenix\n", encoding="utf-8")
    diff_path = tmp_path / "diff.json"
    raw_backup = tmp_path / "t.raw.md"

    fake_agent = MagicMock()
    fake_agent.correct.return_value = CorrectionResult(
        corrected_text="[00:00:01] 小王您好。\n[00:00:05] Phoenix 產品。",
        diffs=[
            CorrectionDiff(original="肖王", corrected="小王", matched_term="小王", timestamp="00:00:01"),
            CorrectionDiff(original="菲尼克斯", corrected="Phoenix", matched_term="Phoenix", timestamp="00:00:05"),
        ],
    )

    correct_transcript(
        transcript_path=str(src),
        glossary_path=str(glossary_path),
        diff_path=str(diff_path),
        raw_backup_path=str(raw_backup),
        agent=fake_agent,
        chunk_chars=1000,
    )

    assert "小王" in src.read_text(encoding="utf-8")
    assert "Phoenix" in src.read_text(encoding="utf-8")
    assert "肖王" in raw_backup.read_text(encoding="utf-8")
    import json
    diffs = json.loads(diff_path.read_text(encoding="utf-8"))
    assert len(diffs) == 2
    assert diffs[0]["matched_term"] == "小王"


def test_skip_when_glossary_empty(tmp_path):
    src = tmp_path / "t.md"
    src.write_text("[00:00:01] x\n", encoding="utf-8")
    glossary_path = tmp_path / "glossary.md"
    glossary_path.write_text("\n  \n", encoding="utf-8")
    diff_path = tmp_path / "diff.json"
    raw_backup = tmp_path / "t.raw.md"

    fake_agent = MagicMock()
    correct_transcript(
        transcript_path=str(src),
        glossary_path=str(glossary_path),
        diff_path=str(diff_path),
        raw_backup_path=str(raw_backup),
        agent=fake_agent,
        chunk_chars=1000,
    )
    fake_agent.correct.assert_not_called()
    assert not raw_backup.exists()
