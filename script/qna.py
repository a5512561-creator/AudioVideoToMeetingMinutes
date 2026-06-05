"""Terminal Q&A to confirm LLM-derived minutes before emailing.

Pure interaction: takes an initial FinalizedMinutes (defaults) and returns a
user-confirmed one. `inp`/`out` are injected so the flow is unit-testable.
Empty input always keeps the shown default — unknown fields are NEVER inferred.
"""
from script.schemas import (
    FinalizedMinutes, FinalTopic, FinalAction, MeetingMeta,
)


def _ask(inp, label, default=""):
    shown = f"{label}" + (f" [{default}]" if default else "")
    val = inp(f"{shown}: ").strip()
    return val if val else default


def _confirm_topics(inp, out, topics):
    kept = []
    for i, t in enumerate(topics, 1):
        out(f"\n[決議 {i}] 項目：{t.item}\n          摘要：{t.summary}")
        choice = inp("  [Enter=保留 / e=改寫 / d=刪除]: ").strip().lower()
        if choice == "d":
            continue
        if choice == "e":
            item = _ask(inp, "  新項目", t.item)
            summary = _ask(inp, "  新摘要", t.summary)
            kept.append(FinalTopic(item=item, summary=summary))
        else:
            kept.append(t)
    while inp("\n新增決議項目? (y/N): ").strip().lower() == "y":
        item = _ask(inp, "  項目")
        summary = _ask(inp, "  摘要")
        kept.append(FinalTopic(item=item, summary=summary))
    return kept


def _confirm_actions(inp, out, actions):
    kept = []
    for i, a in enumerate(actions, 1):
        out(f"\n[Action {i}] 任務：{a.task}\n           負責人：{a.owner} / 到期日：{a.due}")
        choice = inp("  [Enter=保留 / e=改寫任務 / d=刪除]: ").strip().lower()
        if choice == "d":
            continue
        task = _ask(inp, "  新任務", a.task) if choice == "e" else a.task
        owner = _ask(inp, "  負責人", a.owner)
        due = _ask(inp, "  到期日", a.due)
        note = _ask(inp, "  備註", a.note)
        kept.append(FinalAction(task=task, owner=owner, due=due, note=note))
    while inp("\n新增 action? (y/N): ").strip().lower() == "y":
        task = _ask(inp, "  任務")
        owner = _ask(inp, "  負責人")
        due = _ask(inp, "  到期日")
        note = _ask(inp, "  備註")
        kept.append(FinalAction(task=task, owner=owner, due=due, note=note))
    return kept


def run_qna(initial: FinalizedMinutes, *, inp=input, out=print) -> FinalizedMinutes:
    out("=== 會議資訊（直接 Enter 採用預設；空白＝不填，不推論）===")
    subject = _ask(inp, "主旨", initial.subject)
    m = initial.meta
    meta = MeetingMeta(
        meeting_date=_ask(inp, "會議日期", m.meeting_date),
        duration_hint=m.duration_hint,
        meeting_time=_ask(inp, "會議時間 (如 16:00 - 18:00)", m.meeting_time),
        location=_ask(inp, "會議地點 / 會議室", m.location),
        attendees=_ask(inp, "參與人員", m.attendees),
        recorder=_ask(inp, "記錄人", m.recorder),
        doc_links=_ask(inp, "會議文件", m.doc_links),
        video_links=_ask(inp, "會議錄影", m.video_links),
        jira=_ask(inp, "JIRA連結 (optional)", m.jira),
        llm_model=_ask(inp, "整理工具 (LLM)", m.llm_model),
    )
    out("\n=== 逐項確認會議記錄與決議 ===")
    topics = _confirm_topics(inp, out, initial.topics)
    out("\n=== 逐項確認 Action Items（請確認負責人、到期日）===")
    actions = _confirm_actions(inp, out, initial.actions)
    return FinalizedMinutes(meta=meta, subject=subject,
                            topics=topics, actions=actions)
