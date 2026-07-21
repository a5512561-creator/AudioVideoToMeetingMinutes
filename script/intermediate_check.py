"""LLM-free validation of the hand-written intermediate JSON (engine B).

Engine B (the Claude session) writes minutes.json / review.json /
synthesized.json to match the schemas, then runs `--rerender`. This validates
each file up front and returns a friendly per-file report so a shape mistake
surfaces clearly instead of a raw pydantic traceback.
"""
import json
from pathlib import Path

from pydantic import ValidationError

from script.schemas import MeetingMinutes, ReviewResult, SynthesizedMinutes

# filename stem -> schema
_SCHEMAS = {
    "minutes": MeetingMinutes,
    "review": ReviewResult,
    "synthesized": SynthesizedMinutes,
}


def validate_intermediate(out_dir) -> dict:
    """Validate intermediate/{minutes,review,synthesized}.json against schemas.

    Returns {"ok": bool, "files": {stem: {"ok": bool, "error": str}}}.
    """
    inter = Path(out_dir) / "intermediate"
    files: dict[str, dict] = {}
    for stem, schema in _SCHEMAS.items():
        path = inter / f"{stem}.json"
        if not path.exists():
            files[stem] = {"ok": False, "error": f"找不到 {path}"}
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            files[stem] = {"ok": False, "error": f"讀取失敗：{e}"}
            continue
        try:
            json.loads(text)  # surface malformed JSON with a clear syntax message
        except json.JSONDecodeError as e:
            files[stem] = {"ok": False,
                           "error": f"JSON 語法錯誤（行 {e.lineno} 欄 {e.colno}）：{e.msg}"}
            continue
        try:
            schema.model_validate_json(text)
            files[stem] = {"ok": True, "error": ""}
        except ValidationError as e:
            files[stem] = {"ok": False, "error": str(e)}
    return {"ok": all(f["ok"] for f in files.values()), "files": files}
