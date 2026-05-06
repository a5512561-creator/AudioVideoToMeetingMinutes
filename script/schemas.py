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


class ChunkExtract(BaseModel):
    topics: list[str]
    conclusions: list[Conclusion]
    actions: list[Action]


class MeetingMinutes(BaseModel):
    conclusions: list[Conclusion]
    actions: list[Action]


class ReviewNote(BaseModel):
    target_section: Literal["conclusion", "action"]
    target_id: str
    category: Literal["conflict", "ambiguity", "unreasonable", "ok"]
    severity: Literal["info", "warn", "error"]
    note: str
    suggestion: str


class ReviewResult(BaseModel):
    notes: list[ReviewNote]
