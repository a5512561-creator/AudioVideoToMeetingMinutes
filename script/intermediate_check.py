"""LLM-free validation of the hand-written intermediate JSON (engine B).

Engine B (the Claude session) writes minutes.json / review.json /
synthesized.json to match the schemas, then runs `--rerender`. This validates
each file up front and returns a friendly per-file report so a shape mistake
surfaces clearly instead of a raw pydantic traceback.
"""
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
            schema.model_validate_json(path.read_text(encoding="utf-8"))
            files[stem] = {"ok": True, "error": ""}
        except ValidationError as e:
            files[stem] = {"ok": False, "error": str(e)}
        except (ValueError, OSError) as e:
            files[stem] = {"ok": False, "error": f"JSON 解析失敗：{e}"}
    return {"ok": all(f["ok"] for f in files.values()), "files": files}
