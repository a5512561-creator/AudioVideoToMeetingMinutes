import json
import shutil
from pathlib import Path
from script.schemas import CorrectionResult


def _is_glossary_meaningful(text: str) -> bool:
    """True if glossary has at least one non-comment, non-blank bullet."""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return True
    return False


def _split_by_chars(text: str, chunk_chars: int) -> list[str]:
    """Split transcript text on newlines, accumulating up to chunk_chars per chunk."""
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    buf = ""
    for line in lines:
        if buf and len(buf) + len(line) > chunk_chars:
            chunks.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        chunks.append(buf)
    return chunks


def correct_transcript(
    *,
    transcript_path: str,
    glossary_path: str,
    diff_path: str,
    raw_backup_path: str,
    agent,
    chunk_chars: int,
) -> None:
    glossary = Path(glossary_path).read_text(encoding="utf-8")
    if not _is_glossary_meaningful(glossary):
        return

    raw_text = Path(transcript_path).read_text(encoding="utf-8")
    chunks = _split_by_chars(raw_text, chunk_chars)

    corrected_parts: list[str] = []
    all_diffs: list[dict] = []
    for chunk in chunks:
        result: CorrectionResult = agent.correct(chunk_text=chunk, glossary=glossary)
        corrected_parts.append(result.corrected_text)
        all_diffs.extend([d.model_dump() for d in result.diffs])

    shutil.copyfile(transcript_path, raw_backup_path)
    Path(transcript_path).write_text("\n".join(corrected_parts), encoding="utf-8")
    Path(diff_path).parent.mkdir(parents=True, exist_ok=True)
    Path(diff_path).write_text(
        json.dumps(all_diffs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
