from typing import Literal
from pydantic import BaseModel


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


class ChunkExtract(BaseModel):
    topics: list[str]
    conclusions: list[Conclusion]
    actions: list[Action]
    key_points: list[KeyPoint] = []


class MeetingMinutes(BaseModel):
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
