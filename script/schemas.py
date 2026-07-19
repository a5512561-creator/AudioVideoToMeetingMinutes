from typing import Literal
from pydantic import BaseModel, model_validator


def _unwrap_items(value):
    """Coerce the on-prem `expert` model's ``{"items": [...]}`` wrapper back to a
    bare list. In JSON mode that model sometimes mirrors a JSON-Schema ``array``
    by emitting the literal schema keyword — ``"conclusions": {"items": [...]}``
    — instead of the array itself. The payload is valid JSON but the wrong shape,
    so ``_repair_json`` (which only fixes malformed JSON) can't catch it. Unwrap
    a lone ``{"items": [list]}`` to ``[list]``; leave anything else untouched so
    genuinely-missing fields still fail validation (we never fabricate data)."""
    if isinstance(value, dict) and list(value.keys()) == ["items"] and isinstance(value["items"], list):
        return value["items"]
    return value


class _UnwrapListFields:
    """Mixin: before validation, unwrap any list field the on-prem model wrapped
    as ``{"items": [...]}``. Applied to the response models the flaky `expert`
    endpoint fills (see :func:`_unwrap_items`)."""

    @model_validator(mode="before")
    @classmethod
    def _coerce_wrapped_lists(cls, data):
        if not isinstance(data, dict):
            return data
        for field, info in cls.model_fields.items():
            if field in data:
                data[field] = _unwrap_items(data[field])
        return data


class Conclusion(BaseModel):
    text: str
    is_inferred: bool
    source_quote: str
    source_timestamp: str
    source_speaker: str | None = None


class Action(BaseModel):
    task: str
    owner: str
    due: str
    priority: Literal["high", "medium", "low"]
    # 前因 / 背景 / trigger — why this action exists business-wise. Different
    # from `rationale` (meta — why the LLM marked this an action). Empty
    # string default keeps older cached intermediate JSON loadable.
    context: str = ""
    source_quote: str
    source_timestamp: str
    source_speaker: str | None = None
    rationale: str
    is_inferred: bool
    owner_inferred: bool
    due_inferred: bool
    priority_inferred: bool


class KeyPoint(BaseModel):
    text: str
    is_inferred: bool
    source_quote: str
    source_timestamp: str
    source_speaker: str | None = None


class ChunkExtract(_UnwrapListFields, BaseModel):
    topics: list[str]
    conclusions: list[Conclusion]
    actions: list[Action]
    key_points: list[KeyPoint] = []


class MeetingMinutes(_UnwrapListFields, BaseModel):
    conclusions: list[Conclusion]
    actions: list[Action]
    key_points: list[KeyPoint] = []


class ReviewNote(BaseModel):
    target_section: Literal["conclusion", "action", "key_point"]
    target_id: str
    category: Literal["conflict", "ambiguity", "unreasonable", "ok"]
    severity: Literal["info", "warn", "error"]
    note: str
    suggestion: str


class ReviewResult(BaseModel):
    notes: list[ReviewNote]


class CorrectionDiff(BaseModel):
    original: str
    corrected: str
    matched_term: str
    timestamp: str


class CorrectionResult(BaseModel):
    corrected_text: str
    diffs: list[CorrectionDiff]


class SynthTopic(BaseModel):
    title: str
    summary: str
    decisions: list[str] = []
    source_timestamps: list[str] = []


class SynthAction(BaseModel):
    task: str
    owner: str
    due: str
    priority: Literal["high", "medium", "low"]
    # 前因 / 背景 — carried over (or merged) from the underlying extracted
    # Action.context. UI shows this as "前因" on the action row.
    context: str = ""
    source_timestamps: list[str] = []


class SourceRef(BaseModel):
    label: str
    timestamps: list[str] = []


class MeetingMeta(BaseModel):
    meeting_date: str
    duration_hint: str
    meeting_time: str = ""
    location: str = ""
    attendees: str = ""
    recorder: str = ""
    doc_links: str = ""
    video_links: str = ""
    jira: str = ""
    llm_model: str = ""


class SynthesizedMinutes(BaseModel):
    meta: MeetingMeta | None = None
    topics: list[SynthTopic] = []
    action_items: list[SynthAction] = []
    source_index: list[SourceRef] = []


class FinalTopic(BaseModel):
    item: str
    summary: str
    # Decisions are carried alongside the summary (not folded into it) so the
    # renderers can show them as a distinct, highlighted 決議 block. Defaults
    # to [] so older finalized.json (pre-split) still loads.
    decisions: list[str] = []


class FinalAction(BaseModel):
    task: str
    owner: str
    due: str
    note: str = ""


class FinalizedMinutes(BaseModel):
    meta: MeetingMeta
    subject: str
    topics: list[FinalTopic] = []
    actions: list[FinalAction] = []


class AuditCheckMechanical(BaseModel):
    """One deterministic Layer-1 structural check over SynthesizedMinutes.

    `offending` holds the ids of items that failed the check (e.g. ["A3"]
    for action #3, ["T2.d1"] for topic #2's first decision) so the UI can
    highlight exactly which rows to fix.
    """
    key: str
    label: str
    passed: bool
    offending: list[str] = []


class AuditCheckSemantic(BaseModel):
    """One Layer-2 semantic checklist item, LLM-scored 1-5 with rationale."""
    key: str
    label: str
    score: int
    rationale: str


class SemanticAudit(BaseModel):
    """LLM response model for AuditAgent — the semantic checklist scores."""
    checks: list[AuditCheckSemantic] = []


class AuditResult(BaseModel):
    """Combined audit written to intermediate/audit.json.

    `overall_pass` = all mechanical checks passed (Layer 1). Semantic scores
    never hard-block; the editable page requires a separate "已審閱" ack.
    `reviewed` starts False; the front-end sets it when the user acknowledges.
    """
    mechanical: list[AuditCheckMechanical] = []
    semantic: list[AuditCheckSemantic] = []
    overall_pass: bool = False
    reviewed: bool = False
