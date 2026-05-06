"""Speaker label → real name mapping.

After diarization writes SPEAKER_00, SPEAKER_01... labels, the user can fill
in real names in speaker_map.json and re-run with --rerender to get final
output (Excel + Markdown) with real names — without re-running ASR/LLM.
"""
import json
from pathlib import Path


def write_template(path: str, speaker_labels: list[str]) -> None:
    """Write a speaker_map.json template if it doesn't already exist.

    Each label maps to itself (identity), inviting the user to overwrite the
    value with a real name. Existing files are left alone — the user's edits
    survive subsequent --diarize runs.
    """
    p = Path(path)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    mapping = {label: label for label in sorted(set(speaker_labels))}
    p.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load(path: str) -> dict[str, str]:
    """Load speaker_map.json. Return empty dict if missing."""
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def remap(speaker: str | None, mapping: dict[str, str]) -> str | None:
    """Substitute a single speaker label using the mapping. Pass-through if
    no mapping or no entry."""
    if speaker is None:
        return None
    return mapping.get(speaker, speaker)
