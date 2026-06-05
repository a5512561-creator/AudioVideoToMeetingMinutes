# Finalize → Outlook Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive `finalize` CLI command that collects meeting metadata (no inference), confirms each LLM-derived decision/action item, renders a company-format email, and opens it as an editable Outlook draft (never sent).

**Architecture:** A new `finalize` command reads the cached `synthesized.json` from a prior `process` run, runs a terminal Q&A (`script/qna.py`) over an initial `FinalizedMinutes` (built by `email_writer.synth_to_finalized`), writes `finalized.json`, renders HTML via the updated email template, and opens an Outlook draft via `script/outlook_draft.py` (COM-isolated, with HTML-file fallback).

**Tech Stack:** Python 3.12, Pydantic v2, Typer, Jinja2, pytest, pywin32 (Outlook COM, Windows runtime).

**Spec:** `doc/specs/2026-06-05-finalize-outlook-draft-design.md`

**Conventions:**
- Run tests with: `.venv\Scripts\python.exe -m pytest tests/<file>::<test> -v`
- Tests live in `tests/test_*.py`; CLI tested with `typer.testing.CliRunner`.
- All source under `script/`. Imports use `from script.xxx import ...`.

---

### Task 1: Extend schemas with metadata + finalized models

**Files:**
- Modify: `script/schemas.py` (the `MeetingMeta` class ~line 101; append new models at end)
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_schemas.py`:

```python
def test_meeting_meta_new_fields_default_empty():
    from script.schemas import MeetingMeta
    m = MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h")
    assert m.meeting_time == ""
    assert m.location == ""
    assert m.attendees == ""
    assert m.recorder == ""
    assert m.doc_links == ""
    assert m.video_links == ""
    assert m.jira == ""


def test_finalized_minutes_model():
    from script.schemas import (
        FinalizedMinutes, FinalTopic, FinalAction, MeetingMeta,
    )
    f = FinalizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        subject="會議記錄",
        topics=[FinalTopic(item="主題A", summary="摘要A（決議：X）")],
        actions=[FinalAction(task="做X", owner="Alice", due="6/E", note="")],
    )
    assert f.topics[0].item == "主題A"
    assert f.actions[0].note == ""
    # round-trips through JSON (used for finalized.json persistence)
    assert FinalizedMinutes.model_validate_json(f.model_dump_json()) == f
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_schemas.py::test_finalized_minutes_model -v`
Expected: FAIL with `ImportError: cannot import name 'FinalizedMinutes'`

- [ ] **Step 3: Add fields to `MeetingMeta` and new models**

In `script/schemas.py`, replace the `MeetingMeta` class with:

```python
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
```

Append at the end of the file:

```python
class FinalTopic(BaseModel):
    item: str
    summary: str


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_schemas.py -v`
Expected: PASS (all, including the two new tests)

- [ ] **Step 5: Commit**

```bash
git add script/schemas.py tests/test_schemas.py
git commit -m "feat: add meeting metadata fields and FinalizedMinutes models"
```

---

### Task 2: `synth_to_finalized` converter + new email renderer

**Files:**
- Modify: `script/email_writer.py`
- Modify: `script/templates/minutes_email.html.j2`
- Test: `tests/test_email_writer.py` (replace existing — signature changes)

This task changes `write_email_html` to accept a `FinalizedMinutes`, adds `synth_to_finalized` and `render_email_html`, and aligns the template to the company `.msg` format.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `tests/test_email_writer.py` with:

```python
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, MeetingMeta,
    FinalizedMinutes, FinalTopic, FinalAction,
)
from script.email_writer import (
    synth_to_finalized, render_email_html, write_email_html,
)


def _synth():
    return SynthesizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        topics=[SynthTopic(title="FCS 移除彈性討論",
                           summary="討論是否提供 FCS 移除彈性。",
                           decisions=["此項尚無定論，後續確認"],
                           source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="釐清 FCS 移除需求",
                                  owner="林冠名", due="6/E", priority="high",
                                  source_timestamps=["00:01:27"])],
    )


def _final():
    return FinalizedMinutes(
        meta=MeetingMeta(
            meeting_date="2026/06/04", duration_hint="約 2h",
            meeting_time="16:00 - 18:00", location="R531",
            attendees="Max、Heping", recorder="林冠名",
            doc_links="spec.docx", video_links="rec.mp4", jira="",
        ),
        subject="會議記錄: Channelize",
        topics=[FinalTopic(item="FCS 移除彈性討論",
                           summary="討論是否提供彈性（決議：尚無定論，後續確認）")],
        actions=[FinalAction(task="釐清 FCS 移除需求", owner="林冠名",
                             due="6/E", note="")],
    )


def test_synth_to_finalized_folds_decisions_into_summary():
    f = synth_to_finalized(_synth(), subject="會議記錄", meta=_synth().meta)
    assert f.subject == "會議記錄"
    assert f.topics[0].item == "FCS 移除彈性討論"
    # decision text folded into the summary cell
    assert "決議" in f.topics[0].summary
    assert "尚無定論" in f.topics[0].summary
    # action priority dropped; owner/due carried; note empty
    assert f.actions[0].owner == "林冠名" and f.actions[0].due == "6/E"
    assert f.actions[0].note == ""


def test_email_html_company_format(tmp_path):
    dst = tmp_path / "minutes_email.html"
    write_email_html(_final(), str(dst))
    html = dst.read_text(encoding="utf-8")
    # greeting + signature
    assert "Dear all" in html
    assert "Best regards" in html and "林冠名" in html
    # metadata block, filled values (not placeholders)
    assert "2026/06/04" in html and "16:00 - 18:00" in html and "R531" in html
    assert "____" not in html
    # decision section as table, action table with 備註 and NO 優先級
    assert "會議記錄與決議" in html and "項目" in html and "摘要" in html
    assert "Action Items" in html
    assert "行動項目" in html and "負責人" in html and "到期日" in html and "備註" in html
    assert "優先級" not in html
    assert "釐清 FCS 移除需求" in html and "6/E" in html
    assert "<script" not in html


def test_email_html_blank_fields_render_empty(tmp_path):
    f = _final()
    f.meta.attendees = ""        # unknown -> must stay blank, never inferred
    f.meta.location = ""
    dst = tmp_path / "e.html"
    write_email_html(f, str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "參與人員" in html        # label present
    assert "____" not in html        # but no placeholder filler


def test_email_html_escapes_text(tmp_path):
    f = _final()
    f.topics[0].summary = "風險 <b>注意</b> & 風控"
    dst = tmp_path / "e.html"
    write_email_html(f, str(dst))
    html = dst.read_text(encoding="utf-8")
    assert "&lt;b&gt;" in html and "&amp;" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_email_writer.py -v`
Expected: FAIL with `ImportError: cannot import name 'synth_to_finalized'`

- [ ] **Step 3: Rewrite `script/email_writer.py`**

Replace the entire contents of `script/email_writer.py` with:

```python
"""Company-format meeting-minutes email HTML (paste-into-Outlook safe).

Renders a FinalizedMinutes (user-confirmed content) into semantic HTML with
inline styles and tables — no JS, no CSS classes — matching the company
"會議記錄" email layout. Also converts a raw SynthesizedMinutes into an
initial FinalizedMinutes (decisions folded into the summary cell), used both
as the Q&A starting point and for the process-stage preview email.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from script.schemas import (
    SynthesizedMinutes, MeetingMeta,
    FinalizedMinutes, FinalTopic, FinalAction,
)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def synth_to_finalized(
    synth: SynthesizedMinutes, *, subject: str, meta: MeetingMeta
) -> FinalizedMinutes:
    """Build an initial FinalizedMinutes from raw synthesis output.

    Decisions are folded into the topic summary (company format has no
    separate decision column). Action priority is dropped; note starts empty.
    """
    topics = []
    for t in synth.topics:
        summary = t.summary
        if t.decisions:
            summary = f"{summary}（決議：{'；'.join(t.decisions)}）"
        topics.append(FinalTopic(item=t.title, summary=summary))
    actions = [
        FinalAction(task=a.task, owner=a.owner, due=a.due, note="")
        for a in synth.action_items
    ]
    return FinalizedMinutes(meta=meta, subject=subject,
                            topics=topics, actions=actions)


def render_email_html(final: FinalizedMinutes) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        keep_trailing_newline=False,
    )
    return env.get_template("minutes_email.html.j2").render(f=final, m=final.meta)


def write_email_html(final: FinalizedMinutes, dst: str) -> None:
    html = render_email_html(final)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(html, encoding="utf-8")
```

- [ ] **Step 4: Rewrite the template**

Replace the entire contents of `script/templates/minutes_email.html.j2` with:

```jinja
<div style="font-family:'Microsoft JhengHei',Arial,sans-serif;font-size:14px;color:#222;line-height:1.6;">
<p>Dear all :</p>
<p>
📅 會議日期：{{ m.meeting_date }}<br>
🕒 會議時間：{{ m.meeting_time }}　（{{ m.duration_hint }}）<br>
📍 會議地點 / 會議室：{{ m.location }}<br>
👥 參與人員：{{ m.attendees }}<br>
📝 記錄人：{{ m.recorder }}<br>
會議文件：{{ m.doc_links }}<br>
會議錄影：{{ m.video_links }}<br>
JIRA連結 (optional)：{{ m.jira }}
</p>
<hr>
<h2 style="font-size:17px;border-bottom:2px solid #444;padding-bottom:4px;">1. 會議記錄與決議</h2>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;font-size:13px;">
<tr style="background:#f0f0f0;"><th>No</th><th>項目</th><th>摘要</th></tr>
{% for t in f.topics %}
<tr>
<td style="text-align:center;">{{ loop.index }}</td>
<td>{{ t.item }}</td>
<td>{{ t.summary }}</td>
</tr>
{% endfor %}
</table>
<h2 style="font-size:17px;border-bottom:2px solid #444;padding-bottom:4px;">2. Action Items</h2>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;font-size:13px;">
<tr style="background:#f0f0f0;"><th>No</th><th>行動項目</th><th>負責人</th><th>到期日</th><th>備註</th></tr>
{% for a in f.actions %}
<tr>
<td style="text-align:center;">{{ loop.index }}</td>
<td>{{ a.task }}</td>
<td>{{ a.owner }}</td>
<td>{{ a.due }}</td>
<td>{{ a.note }}</td>
</tr>
{% endfor %}
</table>
<p>Best regards,<br>{{ m.recorder }}</p>
</div>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_email_writer.py -v`
Expected: PASS (all five tests)

- [ ] **Step 6: Commit**

```bash
git add script/email_writer.py script/templates/minutes_email.html.j2 tests/test_email_writer.py
git commit -m "feat: company-format email renderer over FinalizedMinutes"
```

---

### Task 3: Update pipeline's preview-email call

`pipeline.run_pipeline` calls `write_email_html(synth, ...)` twice (rerender branch ~line 136, full branch ~line 268). The signature changed, so both must build a preview `FinalizedMinutes` first.

**Files:**
- Modify: `script/pipeline.py` (import + two call sites)
- Test: `tests/test_pipeline.py` (verify it still produces `minutes_email.html`)

- [ ] **Step 1: Inspect the current call sites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v`
Expected: currently PASS (baseline before change). Note any test asserting on `minutes_email.html`.

- [ ] **Step 2: Update the import in `script/pipeline.py`**

Change line 18 from:

```python
from script.email_writer import write_email_html
```

to:

```python
from script.email_writer import write_email_html, synth_to_finalized
```

- [ ] **Step 3: Update the rerender-branch call (~line 136)**

Replace:

```python
        write_email_html(
            synth, str(out_dir / "minutes_email.html"), meeting_file=src
        )
```

with:

```python
        preview = synth_to_finalized(
            synth, subject=base_name, meta=synth.meta or empty_meta()
        )
        write_email_html(preview, str(out_dir / "minutes_email.html"))
```

- [ ] **Step 4: Update the full-run call (~line 268)**

Replace:

```python
    write_email_html(
        synth, str(out_dir / "minutes_email.html"), meeting_file=src,
    )
```

with:

```python
    preview = synth_to_finalized(synth, subject=base_name, meta=meta)
    write_email_html(preview, str(out_dir / "minutes_email.html"))
```

- [ ] **Step 5: Add the `empty_meta` import (rerender branch uses it)**

`meeting_meta` is already imported for `infer_meeting_date, duration_hint` (line 19). Change that line from:

```python
from script.meeting_meta import infer_meeting_date, duration_hint
```

to:

```python
from script.meeting_meta import infer_meeting_date, duration_hint, empty_meta
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v`
Expected: PASS. If a test asserted old email content (e.g. `優先級`), update that assertion to the new format (`行動項目`, `備註`).

- [ ] **Step 7: Commit**

```bash
git add script/pipeline.py tests/test_pipeline.py
git commit -m "refactor: build preview FinalizedMinutes for pipeline email output"
```

---

### Task 4: Interactive Q&A module

**Files:**
- Create: `script/qna.py`
- Test: `tests/test_qna.py`

`run_qna` edits an *initial* `FinalizedMinutes` (defaults) and returns the confirmed one. `inp`/`out` are injected for testing. Empty input keeps the default (never infers).

Interaction contract (one input line each unless noted):
- Subject, then each meta field, prompted with current value as default; empty line keeps default.
- Each topic: prompt `[Enter=保留 / e=改寫 / d=刪除]`. `e` → ask new item then new summary (empty keeps current). `d` → drop. Then "新增項目? (y/N)" loop.
- Each action: prompt `[Enter=保留 / e=改寫任務 / d=刪除]`. `d` → drop. Otherwise (`e` → ask new task first) ALWAYS ask owner, due, note (defaults shown). Then "新增 action? (y/N)" loop.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_qna.py`:

```python
from script.schemas import (
    FinalizedMinutes, FinalTopic, FinalAction, MeetingMeta,
)
from script.qna import run_qna


def _initial():
    return FinalizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        subject="逐字稿檔名",
        topics=[FinalTopic(item="主題A", summary="摘要A"),
                FinalTopic(item="主題B", summary="摘要B")],
        actions=[FinalAction(task="做X", owner="LLM猜的", due="未知", note="")],
    )


def _feeder(lines):
    it = iter(lines)
    return lambda prompt="": next(it)


def test_meta_questions_fill_and_keep_default():
    inp = _feeder([
        "",                      # subject: keep "逐字稿檔名"
        "",                      # meeting_date: keep
        "16:00 - 18:00",         # meeting_time
        "R531",                  # location
        "Max、Heping",           # attendees
        "林冠名",                # recorder
        "spec.docx",             # doc_links
        "rec.mp4",               # video_links
        "",                      # jira: blank (not inferred)
        "", "n",                 # topic A keep; no more topics... (see below)
        "",                      # topic B keep
        "n",                     # add topic? no
        "", "Alice", "6/E", "",  # action: keep, owner, due, note
        "n",                     # add action? no
    ])
    out = lambda *a, **k: None
    f = run_qna(_initial(), inp=inp, out=out)
    assert f.subject == "逐字稿檔名"
    assert f.meta.meeting_time == "16:00 - 18:00"
    assert f.meta.location == "R531"
    assert f.meta.recorder == "林冠名"
    assert f.meta.jira == ""          # blank stays blank
    assert len(f.topics) == 2
    assert f.actions[0].owner == "Alice" and f.actions[0].due == "6/E"


def test_topic_edit_and_delete_and_add():
    inp = _feeder([
        "x",                     # subject (just to advance — set to "x")
        "", "", "", "", "", "", "", "",  # 8 meta fields after subject: keep all
        "e", "主題A改", "摘要A改",   # topic A: edit
        "d",                          # topic B: delete
        "y", "新主題", "新摘要", "n", # add one topic then stop
        "d",                          # action: delete the only one
        "y", "新任務", "Bob", "今天", "備註X", "n",  # add one action
    ])
    out = lambda *a, **k: None
    f = run_qna(_initial(), inp=inp, out=out)
    assert [t.item for t in f.topics] == ["主題A改", "新主題"]
    assert f.topics[0].summary == "摘要A改"
    assert len(f.actions) == 1
    assert f.actions[0].task == "新任務" and f.actions[0].owner == "Bob"
    assert f.actions[0].due == "今天" and f.actions[0].note == "備註X"


def test_action_keep_still_confirms_owner_due():
    inp = _feeder([
        "", "", "", "", "", "", "", "", "",  # subject + 8 meta: keep
        "", "n",                              # topic A keep, topic B keep handled next
        "",                                   # topic B keep
        "n",                                  # add topic? no
        "",                                   # action: keep task
        "確認負責人", "6/30", "",             # but still asked owner/due/note
        "n",
    ])
    out = lambda *a, **k: None
    f = run_qna(_initial(), inp=inp, out=out)
    assert f.actions[0].task == "做X"          # unchanged
    assert f.actions[0].owner == "確認負責人"   # confirmed/overwritten
    assert f.actions[0].due == "6/30"
```

> Note: the exact number of "keep" inputs must match the field count. The meta sequence after `subject` is: date, time, location, attendees, recorder, doc_links, video_links, jira (8 fields). Topics: 2 items. Action: 1 item. Keep input lists aligned with the implementation below.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_qna.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.qna'`

- [ ] **Step 3: Implement `script/qna.py`**

```python
"""Terminal Q&A to confirm LLM-derived minutes before emailing.

Pure interaction: takes an initial FinalizedMinutes (defaults) and returns a
user-confirmed one. `inp`/`out` are injected so the flow is unit-testable.
Empty input always keeps the shown default — unknown fields are NEVER inferred.
"""
from script.schemas import (
    FinalizedMinutes, FinalTopic, FinalAction, MeetingMeta,
)


def _ask(inp, out, label, default=""):
    shown = f"{label}" + (f" [{default}]" if default else "")
    out(f"{shown}: ")
    val = inp("").strip()
    return val if val else default


def _confirm_topics(inp, out, topics):
    kept = []
    for i, t in enumerate(topics, 1):
        out(f"\n[決議 {i}] 項目：{t.item}\n          摘要：{t.summary}")
        choice = inp("  [Enter=保留 / e=改寫 / d=刪除]: ").strip().lower()
        if choice == "d":
            continue
        if choice == "e":
            item = _ask(inp, out, "  新項目", t.item)
            summary = _ask(inp, out, "  新摘要", t.summary)
            kept.append(FinalTopic(item=item, summary=summary))
        else:
            kept.append(t)
    while inp("\n新增決議項目? (y/N): ").strip().lower() == "y":
        item = _ask(inp, out, "  項目")
        summary = _ask(inp, out, "  摘要")
        kept.append(FinalTopic(item=item, summary=summary))
    return kept


def _confirm_actions(inp, out, actions):
    kept = []
    for i, a in enumerate(actions, 1):
        out(f"\n[Action {i}] 任務：{a.task}\n           負責人：{a.owner} / 到期日：{a.due}")
        choice = inp("  [Enter=保留 / e=改寫任務 / d=刪除]: ").strip().lower()
        if choice == "d":
            continue
        task = _ask(inp, out, "  新任務", a.task) if choice == "e" else a.task
        owner = _ask(inp, out, "  負責人", a.owner)
        due = _ask(inp, out, "  到期日", a.due)
        note = _ask(inp, out, "  備註", a.note)
        kept.append(FinalAction(task=task, owner=owner, due=due, note=note))
    while inp("\n新增 action? (y/N): ").strip().lower() == "y":
        task = _ask(inp, out, "  任務")
        owner = _ask(inp, out, "  負責人")
        due = _ask(inp, out, "  到期日")
        note = _ask(inp, out, "  備註")
        kept.append(FinalAction(task=task, owner=owner, due=due, note=note))
    return kept


def run_qna(initial: FinalizedMinutes, *, inp=input, out=print) -> FinalizedMinutes:
    out("=== 會議資訊（直接 Enter 採用預設；空白＝不填，不推論）===")
    subject = _ask(inp, out, "主旨", initial.subject)
    m = initial.meta
    meta = MeetingMeta(
        meeting_date=_ask(inp, out, "會議日期", m.meeting_date),
        duration_hint=m.duration_hint,
        meeting_time=_ask(inp, out, "會議時間 (如 16:00 - 18:00)", m.meeting_time),
        location=_ask(inp, out, "會議地點 / 會議室", m.location),
        attendees=_ask(inp, out, "參與人員", m.attendees),
        recorder=_ask(inp, out, "記錄人", m.recorder),
        doc_links=_ask(inp, out, "會議文件", m.doc_links),
        video_links=_ask(inp, out, "會議錄影", m.video_links),
        jira=_ask(inp, out, "JIRA連結 (optional)", m.jira),
    )
    out("\n=== 逐項確認會議記錄與決議 ===")
    topics = _confirm_topics(inp, out, initial.topics)
    out("\n=== 逐項確認 Action Items（請確認負責人、到期日）===")
    actions = _confirm_actions(inp, out, initial.actions)
    return FinalizedMinutes(meta=meta, subject=subject,
                            topics=topics, actions=actions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_qna.py -v`
Expected: PASS. If an "keep" sequence is off-by-one, align the test input list to the prompt order in `run_qna` (subject → 8 meta → topics → topics-add → actions → actions-add).

- [ ] **Step 5: Commit**

```bash
git add script/qna.py tests/test_qna.py
git commit -m "feat: interactive Q&A to confirm minutes metadata and items"
```

---

### Task 5: Outlook draft (COM-isolated) with fallback

**Files:**
- Create: `script/outlook_draft.py`
- Test: `tests/test_outlook_draft.py`

`open_draft` is the ONLY pywin32-dependent unit. It must never send, never set recipients, and must swallow any exception (returning `False`) so callers can fall back.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_outlook_draft.py`:

```python
import sys
import types
from unittest.mock import MagicMock
from script.outlook_draft import open_draft


def _install_fake_win32com(dispatch_return):
    """Install a fake win32com.client module; return the created MailItem mock."""
    mod = types.ModuleType("win32com")
    client = types.ModuleType("win32com.client")
    client.Dispatch = MagicMock(return_value=dispatch_return)
    mod.client = client
    sys.modules["win32com"] = mod
    sys.modules["win32com.client"] = client
    return client


def test_open_draft_sets_body_and_displays_without_sending(monkeypatch):
    mail = MagicMock()
    app = MagicMock()
    app.CreateItem.return_value = mail
    _install_fake_win32com(app)

    ok = open_draft("主旨X", "<div>內容</div>")

    assert ok is True
    app.CreateItem.assert_called_once_with(0)      # 0 = olMailItem
    assert mail.Subject == "主旨X"
    assert mail.HTMLBody == "<div>內容</div>"
    mail.Display.assert_called_once()              # opened, not sent
    mail.Send.assert_not_called()
    assert mail.To in ("", None) or not mail.To.called  # recipients untouched


def test_open_draft_returns_false_on_com_error(monkeypatch):
    client = _install_fake_win32com(MagicMock())
    client.Dispatch.side_effect = RuntimeError("no Outlook")
    assert open_draft("s", "<p>x</p>") is False


def test_open_draft_returns_false_when_pywin32_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "win32com", None)
    monkeypatch.setitem(sys.modules, "win32com.client", None)
    assert open_draft("s", "<p>x</p>") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_outlook_draft.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.outlook_draft'`

- [ ] **Step 3: Implement `script/outlook_draft.py`**

```python
"""Open a meeting-minutes email as an editable Outlook draft (never sent).

Isolated wrapper around Outlook COM (pywin32). Any failure — pywin32 not
installed, Outlook not available, COM error — is swallowed and reported as
False so the caller can fall back to the written HTML file.
"""


def open_draft(subject: str, html_body: str) -> bool:
    """Create a new Outlook mail item, set subject + HTML body, and open it
    for editing via Display(). Recipients are intentionally left empty.

    Returns True on success, False on any failure.
    """
    try:
        import win32com.client as win32  # type: ignore
        if win32 is None:                # tests may stub this to None
            return False
        app = win32.Dispatch("Outlook.Application")
        mail = app.CreateItem(0)         # 0 = olMailItem
        mail.Subject = subject
        mail.HTMLBody = html_body
        mail.Display(False)              # open editable window; do NOT Send()
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_outlook_draft.py -v`
Expected: PASS

> If `test_open_draft_returns_false_when_pywin32_missing` fails because the real `win32com` is importable and not None, the `if win32 is None` guard handles the stubbed case; the monkeypatch sets the module to `None`, so `import win32com.client as win32` yields `None`. Keep the guard.

- [ ] **Step 5: Commit**

```bash
git add script/outlook_draft.py tests/test_outlook_draft.py
git commit -m "feat: Outlook draft opener with safe fallback"
```

---

### Task 6: `finalize` orchestrator

**Files:**
- Create: `script/finalize.py`
- Test: `tests/test_finalize.py`

Wires it together: locate `synthesized.json`, build defaults (or load `finalized.json` when `reuse`), run Q&A, persist `finalized.json`, write `minutes_email.html`, open the draft (fall back to a printed notice).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_finalize.py`:

```python
import json
from unittest.mock import patch
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, MeetingMeta,
    FinalizedMinutes, FinalTopic, FinalAction,
)
from script.finalize import run_finalize


def _write_synth(out_dir):
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True)
    synth = SynthesizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h"),
        topics=[SynthTopic(title="主題A", summary="摘要A", decisions=["決議A"])],
        action_items=[SynthAction(task="做X", owner="猜", due="未知", priority="high")],
    )
    (inter / "synthesized.json").write_text(synth.model_dump_json(), encoding="utf-8")


def _confirmed():
    return FinalizedMinutes(
        meta=MeetingMeta(meeting_date="2026/06/04", duration_hint="約 2h",
                         recorder="林冠名"),
        subject="會議記錄: t",
        topics=[FinalTopic(item="主題A", summary="摘要A（決議：決議A）")],
        actions=[FinalAction(task="做X", owner="Alice", due="6/E", note="")],
    )


def test_finalize_writes_json_html_and_opens_draft(tmp_path):
    out_dir = tmp_path / "out" / "t"
    _write_synth(out_dir)
    with patch("script.finalize.run_qna", return_value=_confirmed()) as qna, \
         patch("script.finalize.open_draft", return_value=True) as draft:
        run_finalize(str(out_dir), default_subject="t")
    # qna got an initial FinalizedMinutes with decisions folded in
    initial = qna.call_args.args[0]
    assert isinstance(initial, FinalizedMinutes)
    assert "決議" in initial.topics[0].summary
    assert initial.subject == "t"
    # persisted + rendered
    assert (out_dir / "finalized.json").exists()
    assert (out_dir / "minutes_email.html").exists()
    # draft opened with the confirmed subject + rendered html
    subject_arg, html_arg = draft.call_args.args
    assert subject_arg == "會議記錄: t"
    assert "林冠名" in html_arg and "6/E" in html_arg
    saved = FinalizedMinutes.model_validate_json(
        (out_dir / "finalized.json").read_text(encoding="utf-8"))
    assert saved.actions[0].owner == "Alice"


def test_finalize_missing_synth_raises(tmp_path):
    out_dir = tmp_path / "out" / "missing"
    out_dir.mkdir(parents=True)
    try:
        run_finalize(str(out_dir), default_subject="x")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "process" in str(e)


def test_finalize_reuse_loads_previous_as_defaults(tmp_path):
    out_dir = tmp_path / "out" / "t"
    _write_synth(out_dir)
    prev = _confirmed()
    prev.meta.location = "R531"
    (out_dir / "finalized.json").write_text(prev.model_dump_json(), encoding="utf-8")
    with patch("script.finalize.run_qna", return_value=_confirmed()) as qna, \
         patch("script.finalize.open_draft", return_value=True):
        run_finalize(str(out_dir), default_subject="t", reuse=True)
    initial = qna.call_args.args[0]
    assert initial.meta.location == "R531"     # came from previous finalized.json
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_finalize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.finalize'`

- [ ] **Step 3: Implement `script/finalize.py`**

```python
"""Interactive finalize step: confirm minutes, render email, open Outlook draft.

Reads the cached synthesized.json from a prior `process` run, runs the
terminal Q&A, persists finalized.json, writes minutes_email.html, and opens
an editable Outlook draft (falling back to the HTML file if Outlook is
unavailable). Runs no LLM calls.
"""
from pathlib import Path

from script.schemas import SynthesizedMinutes, FinalizedMinutes
from script.email_writer import synth_to_finalized, render_email_html, write_email_html
from script.qna import run_qna
from script.outlook_draft import open_draft
from script.meeting_meta import empty_meta


def run_finalize(out_dir: str, *, default_subject: str, reuse: bool = False,
                 inp=input, out=print) -> None:
    out_path = Path(out_dir)
    synth_path = out_path / "intermediate" / "synthesized.json"
    if not synth_path.exists():
        raise RuntimeError(
            f"找不到 {synth_path} — 請先對此會議跑 `process` 產生會議記錄。"
        )
    synth = SynthesizedMinutes.model_validate_json(
        synth_path.read_text(encoding="utf-8"))

    finalized_path = out_path / "finalized.json"
    if reuse and finalized_path.exists():
        initial = FinalizedMinutes.model_validate_json(
            finalized_path.read_text(encoding="utf-8"))
    else:
        initial = synth_to_finalized(
            synth, subject=default_subject, meta=synth.meta or empty_meta())

    final = run_qna(initial, inp=inp, out=out)

    finalized_path.write_text(final.model_dump_json(), encoding="utf-8")
    html_path = out_path / "minutes_email.html"
    write_email_html(final, str(html_path))

    if open_draft(final.subject, render_email_html(final)):
        out(f"\n✅ 已開啟 Outlook 草稿（未寄出）。同時輸出：{html_path}")
    else:
        out(f"\n⚠️ 無法開啟 Outlook 草稿；已輸出 HTML，請手動開啟：{html_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_finalize.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add script/finalize.py tests/test_finalize.py
git commit -m "feat: finalize orchestrator wiring Q&A, render, and Outlook draft"
```

---

### Task 7: `finalize` CLI command

**Files:**
- Modify: `script/main.py` (add a second `@app.command()`)
- Test: `tests/test_main.py` (add cases)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_main.py`:

```python
def test_cli_finalize_resolves_name_and_calls_run(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_finalize") as run:
        result = runner.invoke(app, ["finalize", "transcript.txt", "--name", "t"])
    assert result.exit_code == 0, result.output
    kwargs = run.call_args.kwargs
    args = run.call_args.args
    # out_dir resolves under OUT_DIR/<name>
    assert args[0].replace("\\", "/").endswith("out/t")
    assert kwargs["default_subject"] == "transcript.txt"  # default subject = src basename
    assert kwargs["reuse"] is False


def test_cli_finalize_reuse_flag(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    with patch("script.main.run_finalize") as run:
        result = runner.invoke(app, ["finalize", "x.txt", "--name", "t", "--reuse"])
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["reuse"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -k finalize -v`
Expected: FAIL — `finalize` is not a known command (exit code != 0) or `run_finalize` not importable.

- [ ] **Step 3: Add the command to `script/main.py`**

Add the import near the top (after `from script.pipeline import run_pipeline`):

```python
from pathlib import Path
from script.finalize import run_finalize
```

Add a new command after the existing `process` function:

```python
@app.command()
def finalize(
    src: str = typer.Argument(..., help="逐字稿路徑或既有輸出資料夾名（用來定位 out/<name>）。"),
    name: str | None = typer.Option(None, "--name", help="輸出資料夾名（預設取 src basename）。"),
    reuse: bool = typer.Option(
        False, "--reuse",
        help="沿用上次 finalized.json 當 Q&A 預設值（避免重問）。"),
) -> None:
    """互動式確認會議記錄並開啟 Outlook 草稿（不寄出）。"""
    settings = Settings()
    base_name = name or Path(src).stem
    out_dir = str(Path(settings.out_dir) / base_name)
    run_finalize(out_dir, default_subject=Path(src).stem, reuse=reuse)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: PASS (existing `process` tests + the two new `finalize` tests)

- [ ] **Step 5: Commit**

```bash
git add script/main.py tests/test_main.py
git commit -m "feat: add finalize CLI command"
```

---

### Task 8: Add pywin32 dependency + run helper + docs

**Files:**
- Modify: `requirements.txt` (or `pyproject.toml` — whichever the repo uses)
- Modify: `run.ps1` (optional convenience: a finalize entry) — SKIP if out of scope
- Modify: `README.md`

- [ ] **Step 1: Locate the dependency file**

Run: `.venv\Scripts\python.exe -m pip show pywin32`
If "WARNING: Package(s) not found", it must be added and installed.

- [ ] **Step 2: Add pywin32 to requirements**

Append `pywin32` to `requirements.txt` (create the line if the file lists deps; match existing pin style — unpinned is acceptable if others are).

- [ ] **Step 3: Install it**

Run: `.venv\Scripts\python.exe -m pip install pywin32`
Expected: "Successfully installed pywin32-..."

- [ ] **Step 4: Verify the draft works end-to-end against the existing run**

Run: `.venv\Scripts\python.exe -m script.main finalize "src\20260604_0630pm_Switch_RXDMA_水位異常_CFT_除錯方案討論.txt" --name 20260604_Switch_RXDMA_CFT`
Expected: Q&A prompts appear; after answering, an Outlook draft window opens (not sent), and `out\20260604_Switch_RXDMA_CFT\minutes_email.html` + `finalized.json` are written.

> This step is interactive; run it manually. If running non-interactively, pipe answers via stdin or skip and rely on Task 6 tests.

- [ ] **Step 5: Update README**

Add a short "Finalize（互動確認 + Outlook 草稿）" section documenting:
- Prereq: Windows + Outlook desktop + pywin32.
- Usage: `python -m script.main finalize <src> --name <name>` (after `process`).
- `--reuse` to reuse previous answers.
- Behaviour: opens an editable draft, never sends; unknown fields left blank (not inferred).

- [ ] **Step 6: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt README.md
git commit -m "build: add pywin32 dep and document finalize command"
```

---

## Self-Review

**Spec coverage:**
- §2 company format → Task 2 (template) ✓
- §4.1 schemas → Task 1 ✓
- §4.2 qna → Task 4 ✓
- §4.3 outlook_draft → Task 5 ✓
- §4.4 template → Task 2 ✓
- §4.5 email_writer + pipeline preview → Tasks 2, 3 ✓
- §4.6 finalize command → Tasks 6, 7 ✓
- §4.7 pywin32 dep → Task 8 ✓
- §6 error handling (missing synth → RuntimeError; COM fail → fallback) → Tasks 5, 6 ✓
- §7 tests (qna, template, outlook) → Tasks 2, 4, 5 ✓

**Type consistency:** `FinalizedMinutes`/`FinalTopic`(item,summary)/`FinalAction`(task,owner,due,note) used identically across Tasks 1, 2, 4, 6, 7. `synth_to_finalized(synth, *, subject, meta)`, `render_email_html(final)`, `write_email_html(final, dst)`, `run_qna(initial, *, inp, out)`, `open_draft(subject, html_body)`, `run_finalize(out_dir, *, default_subject, reuse, inp, out)` — signatures consistent between definition and call sites.

**Placeholder scan:** No TBD/TODO; every code step has full code. Task 8 Step 4 is explicitly interactive and marked manual.

**Note on Ctrl-C (spec §6):** `run_finalize` writes `finalized.json` only after `run_qna` returns, so a Ctrl-C during Q&A leaves no partial file — satisfied by ordering, no extra code needed.
