"""Self-contained HTML output for meeting minutes.

Replaces the Excel writer as the primary output: a single .html file with
tab navigation, speaker filter, search box, and collapsible source quotes.
Easier to navigate than a 100-row Excel sheet for long meetings.
"""
import os
from pathlib import Path
from collections import Counter

from jinja2 import Environment, FileSystemLoader

from script.schemas import MeetingMinutes, ReviewResult, ReviewNote
from script.speaker_map import remap as _remap, remap_text as _remap_text


_TEMPLATE_DIR = Path(__file__).parent / "templates"

_SECTION_LABEL = {"conclusion": "結論", "key_point": "重點", "action": "Action"}
_SEV_ICON = {"info": "✅", "warn": "⚠️", "error": "❌"}


def _hue(name: str) -> int:
    """Map a speaker name to a stable HSL hue (0–359)."""
    return sum(ord(c) for c in name) % 360


def _index_review(review: ReviewResult) -> dict:
    return {(n.target_section, n.target_id): n for n in review.notes}


def _format_review_badge(note: ReviewNote | None, sm: dict) -> dict | None:
    if note is None:
        return None
    if note.category == "ok":
        return {"icon": "✅", "label": "OK", "severity": "info"}
    return {
        "icon": _SEV_ICON.get(note.severity, ""),
        "label": f"{note.category}：{_remap_text(note.note, sm)}",
        "severity": note.severity,
    }


def _conclusion_view(c, i, rev, sm):
    speaker = _remap(c.source_speaker, sm) or ""
    return {
        "id": f"C{i}",
        "text": _remap_text(c.text, sm),
        "is_inferred": c.is_inferred,
        "source_quote": _remap_text(c.source_quote, sm),
        "source_timestamp": c.source_timestamp,
        "speaker": speaker,
        "hue": _hue(speaker) if speaker else 0,
        "review_badge": _format_review_badge(rev, sm),
    }


def _keypoint_view(k, i, rev, sm):
    speaker = _remap(k.source_speaker, sm) or ""
    return {
        "id": f"K{i}",
        "text": _remap_text(k.text, sm),
        "is_inferred": k.is_inferred,
        "source_quote": _remap_text(k.source_quote, sm),
        "source_timestamp": k.source_timestamp,
        "speaker": speaker,
        "hue": _hue(speaker) if speaker else 0,
        "review_badge": _format_review_badge(rev, sm),
    }


def _action_view(a, i, rev, sm):
    speaker = _remap(a.source_speaker, sm) or ""
    return {
        "id": f"A{i}",
        "task": _remap_text(a.task, sm),
        "is_inferred": a.is_inferred,
        "owner": _remap_text(a.owner, sm),
        "owner_inferred": a.owner_inferred,
        "due": a.due,
        "due_inferred": a.due_inferred,
        "priority": a.priority,
        "priority_inferred": a.priority_inferred,
        "rationale": _remap_text(a.rationale, sm),
        "source_quote": _remap_text(a.source_quote, sm),
        "source_timestamp": a.source_timestamp,
        "speaker": speaker,
        "hue": _hue(speaker) if speaker else 0,
        "review_badge": _format_review_badge(rev, sm),
    }


def _speaker_distribution(conclusions, key_points, actions) -> Counter:
    c: Counter = Counter()
    for items in (conclusions, key_points, actions):
        for item in items:
            sp = item["speaker"]
            if sp:
                c[sp] += 1
    return c


def write_minutes_html(
    minutes: MeetingMinutes,
    review: ReviewResult,
    dst: str,
    *,
    meeting_file: str,
    diarization_enabled: bool,
    speakers_detected: int,
    speaker_map: dict[str, str] | None = None,
) -> None:
    """Write a self-contained HTML meeting-minutes file.

    Parameters
    ----------
    minutes:             Structured minutes output from LLM.
    review:              Review notes (info / warn / error) from reviewer agent.
    dst:                 Destination file path (will be created/overwritten).
    meeting_file:        Original media filename shown in the header.
    diarization_enabled: Whether speaker diarization was active.
    speakers_detected:   Number of distinct speakers found during diarization.
    speaker_map:         Optional SPEAKER_NN → real name mapping.
    """
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    sm = speaker_map or {}

    review_ix = _index_review(review)

    conclusions_view = [
        _conclusion_view(c, i, review_ix.get(("conclusion", f"C{i}")), sm)
        for i, c in enumerate(minutes.conclusions, start=1)
    ]
    key_points_view = [
        _keypoint_view(k, i, review_ix.get(("key_point", f"K{i}")), sm)
        for i, k in enumerate(minutes.key_points, start=1)
    ]
    actions_view = [
        _action_view(a, i, review_ix.get(("action", f"A{i}")), sm)
        for i, a in enumerate(minutes.actions, start=1)
    ]

    review_summary = [
        {
            "id": n.target_id,
            "section": _SECTION_LABEL[n.target_section],
            "category": n.category,
            "severity": n.severity,
            "icon": _SEV_ICON.get(n.severity, ""),
            "note": _remap_text(n.note, sm) or "",
            "suggestion": _remap_text(n.suggestion, sm) or "",
        }
        for n in review.notes
        if n.severity in ("warn", "error")
    ]

    speaker_counts = _speaker_distribution(conclusions_view, key_points_view, actions_view)
    all_speakers = sorted(speaker_counts.keys(), key=lambda s: -speaker_counts[s])
    speakers_ctx = [(name, speaker_counts[name], _hue(name)) for name in all_speakers]

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    tpl = env.get_template("minutes.html.j2")
    html = tpl.render(
        meeting_file=os.path.basename(meeting_file) or meeting_file,
        diarization_enabled=diarization_enabled,
        speakers_detected=speakers_detected,
        n_conclusions=len(conclusions_view),
        n_keypoints=len(key_points_view),
        n_actions=len(actions_view),
        n_warns=sum(1 for n in review.notes if n.severity == "warn"),
        n_errors=sum(1 for n in review.notes if n.severity == "error"),
        n_oks=sum(1 for n in review.notes if n.severity == "info"),
        conclusions=conclusions_view,
        key_points=key_points_view,
        actions=actions_view,
        review_summary=review_summary,
        speakers=speakers_ctx,
    )
    Path(dst).write_text(html, encoding="utf-8")
