"""Deterministic Layer-1 structural audit over SynthesizedMinutes.

Pure Python, no LLM, no I/O. These checks are the ones the editable HTML
re-runs live in JS to block export (P3), so they must stay deterministic and
trivially portable. `offending` ids: actions are A1..An (1-based), topics are
T1..Tn, a topic's decisions are T{n}.d{m}, and placeholder hits are dotted
field paths like "A1.task" / "T1.summary".
"""
from script.schemas import SynthesizedMinutes, AuditCheckMechanical

# Any of these appearing in a text field means the content is not final.
PLACEHOLDER_MARKERS = ("[待確認]", "待確認", "TODO", "TBD", "待補", "待補充")


def _blank(s: str | None) -> bool:
    return not (s or "").strip()


def _has_marker(s: str | None) -> bool:
    v = s or ""
    return any(m in v for m in PLACEHOLDER_MARKERS)


def evaluate(synth: SynthesizedMinutes) -> list[AuditCheckMechanical]:
    topics = synth.topics
    actions = synth.action_items

    def check(key, label, offending):
        return AuditCheckMechanical(
            key=key, label=label, passed=not offending, offending=offending)

    checks: list[AuditCheckMechanical] = []

    checks.append(check(
        "action_owner_present", "每個 Action 有負責人（不得空）",
        [f"A{i}" for i, a in enumerate(actions, 1) if _blank(a.owner)]))

    checks.append(check(
        "action_due_present", "每個 Action 有期限（不得空）",
        [f"A{i}" for i, a in enumerate(actions, 1) if _blank(a.due)]))

    checks.append(check(
        "decision_nonempty", "每條決議非空",
        [f"T{i}.d{j}"
         for i, t in enumerate(topics, 1)
         for j, d in enumerate(t.decisions, 1) if _blank(d)]))

    checks.append(check(
        "topic_title_nonempty", "每個議題有標題",
        [f"T{i}" for i, t in enumerate(topics, 1) if _blank(t.title)]))

    checks.append(check(
        "topic_summary_nonempty", "每個議題有摘要",
        [f"T{i}" for i, t in enumerate(topics, 1) if _blank(t.summary)]))

    marker_hits: list[str] = []
    for i, t in enumerate(topics, 1):
        if _has_marker(t.title):
            marker_hits.append(f"T{i}.title")
        if _has_marker(t.summary):
            marker_hits.append(f"T{i}.summary")
        for j, d in enumerate(t.decisions, 1):
            if _has_marker(d):
                marker_hits.append(f"T{i}.d{j}")
    for i, a in enumerate(actions, 1):
        for field in ("task", "owner", "due", "context"):
            if _has_marker(getattr(a, field, "")):
                marker_hits.append(f"A{i}.{field}")
    checks.append(check(
        "no_placeholder_markers", "無殘留待確認 / TODO 標記", marker_hits))

    return checks


def overall_pass(checks: list[AuditCheckMechanical]) -> bool:
    return all(c.passed for c in checks)
