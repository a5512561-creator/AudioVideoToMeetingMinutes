# Meeting-Minutes Synthesis + Email HTML — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-reduce LLM "synthesis" stage that consolidates the extracted minutes into topic-grouped decisions + a real Action table, and render it into a paste-into-Outlook email HTML matching the team template.

**Architecture:** Additive. New `SynthesizedMinutes` schema, a `SynthesisAgent` (consumes reduced `minutes.json`), a `meeting_meta` util (date/duration), and an `email_writer` (simple inline-styled HTML, no JS). `pipeline.py` gains Stage 5 between Review and the token-aggregate block; existing `minutes.html` / `review_report.md` and all map/reduce behavior stay untouched.

**Tech Stack:** Python, pydantic, instructor, jinja2, pytest.

Spec: `doc/specs/2026-05-19-email-minutes-synthesis-design.md`. Branch: `feat/email-minutes-synthesis`. Run pytest from repo root with `.venv\Scripts\python.exe -m pytest`. Each task ends with the full suite green.

---

### Task 1: SynthesizedMinutes schema

**Files:**
- Modify: `script/schemas.py` (append at end)
- Test: `tests/test_schemas.py` (append at end)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_schemas.py`:

```python
from script.schemas import (
    SynthTopic, SynthAction, SourceRef, MeetingMeta, SynthesizedMinutes,
)


def test_synth_topic_defaults():
    t = SynthTopic(title="KPI 訂定", summary="討論摘要")
    assert t.decisions == [] and t.source_timestamps == []


def test_synth_action_priority_enum():
    a = SynthAction(task="試算 KTR", owner="未明", due="未明", priority="high")
    assert a.source_timestamps == []
    with pytest.raises(ValidationError):
        SynthAction(task="x", owner="未明", due="未明", priority="urgent")


def test_synthesized_minutes_meta_optional_and_nested():
    sm = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s", decisions=["d"])],
        action_items=[SynthAction(task="x", owner="未明", due="未明", priority="low")],
        source_index=[SourceRef(label="決議 1", timestamps=["00:08:34"])],
    )
    assert sm.meta is None
    sm.meta = MeetingMeta(meeting_date="2026/05/18", duration_hint="逐字稿長度約 1h 55m")
    assert sm.meta.meeting_date == "2026/05/18"
    assert sm.topics[0].decisions == ["d"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_schemas.py -q`
Expected: FAIL — `ImportError: cannot import name 'SynthTopic'`.

- [ ] **Step 3: Append to `script/schemas.py`**

(`Literal` and `BaseModel` are already imported at the top of the file.)

```python


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
    source_timestamps: list[str] = []


class SourceRef(BaseModel):
    label: str
    timestamps: list[str] = []


class MeetingMeta(BaseModel):
    meeting_date: str
    duration_hint: str


class SynthesizedMinutes(BaseModel):
    meta: MeetingMeta | None = None
    topics: list[SynthTopic] = []
    action_items: list[SynthAction] = []
    source_index: list[SourceRef] = []
```

> Design note: `meta` is `None`-defaulted so the synthesis LLM does not have to produce date/duration (it cannot know them). The pipeline computes `MeetingMeta` and assigns it after the LLM call (Task 3 / Task 5).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_schemas.py -q`
Expected: PASS (all schema tests, old + new).

- [ ] **Step 5: Commit**

```bash
git add script/schemas.py tests/test_schemas.py
git commit -m "feat: SynthesizedMinutes schema (topics/actions/source_index/meta)"
```

---

### Task 2: meeting_meta utility (date + duration)

**Files:**
- Create: `script/meeting_meta.py`
- Test: `tests/test_meeting_meta.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_meeting_meta.py`:

```python
from script.meeting_meta import infer_meeting_date, duration_hint


def test_date_from_8digit_in_name():
    assert infer_meeting_date("20260518_leadersync", "x.txt") == "2026/05/18"


def test_date_from_separated_in_src_when_name_missing():
    assert infer_meeting_date(None, r"D:\m\2026-05-18 meeting.txt") == "2026/05/18"


def test_date_name_takes_precedence_over_src():
    assert infer_meeting_date("20260101_x", r"D:\m\20251231.txt") == "2026/01/01"


def test_date_fallback_placeholder():
    assert infer_meeting_date("leadersync", "meeting.txt") == "YYYY/MM/DD"


def test_duration_hint_from_span():
    md = "[00:00:00] a\n[00:10:00] b\n[01:55:14] c\n"
    assert duration_hint(md) == "逐字稿長度約 1h 55m"


def test_duration_hint_no_timestamps():
    assert duration_hint("no timestamps here\n") == "逐字稿長度未知"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_meeting_meta.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'script.meeting_meta'`.

- [ ] **Step 3: Create `script/meeting_meta.py`**

```python
"""Best-effort meeting metadata the transcript itself cannot supply.

Date is inferred from the output name / source filename; meeting duration
is a *hint* derived from the transcript timestamp span (NOT wall-clock).
"""
import re
from pathlib import Path

_DATE_SEP = re.compile(r"(20\d{2})[-/](\d{2})[-/](\d{2})")
_DATE_8 = re.compile(r"(20\d{2})(\d{2})(\d{2})")
_TS = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\]")


def infer_meeting_date(name: str | None, src: str) -> str:
    """Return 'YYYY/MM/DD' from name/src basename, else the literal
    placeholder 'YYYY/MM/DD'. `name` wins over `src`."""
    for cand in ([name] if name else []) + [Path(src).stem]:
        m = _DATE_SEP.search(cand) or _DATE_8.search(cand)
        if m:
            return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return "YYYY/MM/DD"


def duration_hint(transcript_md_text: str) -> str:
    """Hint string from the [HH:MM:SS] span; '逐字稿長度未知' if none."""
    ts = _TS.findall(transcript_md_text)
    if not ts:
        return "逐字稿長度未知"
    secs = [int(h) * 3600 + int(m) * 60 + int(s) for h, m, s in ts]
    span = max(secs) - min(secs)
    h, rem = divmod(span, 3600)
    return f"逐字稿長度約 {h}h {rem // 60}m"
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_meeting_meta.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add script/meeting_meta.py tests/test_meeting_meta.py
git commit -m "feat: meeting_meta (infer date + transcript duration hint)"
```

---

### Task 3: SynthesisAgent + prompts

**Files:**
- Create: `script/prompts/synthesis_system.j2`
- Create: `script/prompts/synthesis_user.j2`
- Create: `script/agents/synthesis_agent.py`
- Test: `tests/test_synthesis_agent.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_synthesis_agent.py`:

```python
from unittest.mock import MagicMock, patch
from script.schemas import (
    Conclusion, Action, MeetingMinutes, MeetingMeta,
    SynthesizedMinutes, SynthTopic, SynthAction,
)
from script.agents.synthesis_agent import SynthesisAgent


def _conc():
    return Conclusion(text="KPI 不納入考核", is_inferred=False, source_quote="q",
                       source_timestamp="00:05:50", source_speaker=None)


def _act():
    return Action(task="試算 KTR", owner="未明", due="兩週後", priority="high",
                  source_quote="q", source_timestamp="00:01:27", source_speaker=None,
                  rationale="r", is_inferred=False, owner_inferred=True,
                  due_inferred=False, priority_inferred=True)


def _make_agent():
    with patch("script.agents.synthesis_agent.LLMAgent.__init__", return_value=None):
        a = SynthesisAgent.__new__(SynthesisAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        return a


def test_synthesize_passes_minutes_json_and_injects_meta():
    a = _make_agent()
    llm_out = SynthesizedMinutes(
        topics=[SynthTopic(title="KPI", summary="s", decisions=["d"],
                            source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="試算 KTR", owner="未明", due="兩週後",
                                   priority="high", source_timestamps=["00:01:27"])],
    )
    assert llm_out.meta is None
    a.call.return_value = llm_out
    minutes = MeetingMinutes(conclusions=[_conc()], actions=[_act()])
    meta = MeetingMeta(meeting_date="2026/05/18", duration_hint="逐字稿長度約 1h 55m")

    out = a.synthesize(minutes, meta)

    assert out is llm_out
    assert out.meta == meta  # pipeline-owned meta injected post-call
    # the reduced minutes JSON was handed to the user template
    user_ctx = a.render.call_args_list[1].kwargs
    assert "KPI 不納入考核" in user_ctx["minutes_json"]
    # response_model is the synthesized schema
    assert a.call.call_args.kwargs["response_model"] is SynthesizedMinutes
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_synthesis_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'script.agents.synthesis_agent'`.

- [ ] **Step 3: Create the prompts and agent**

Create `script/prompts/synthesis_system.j2`:

```jinja
你是一位資深會議記錄編輯。輸入是「同一場會議已抽取並去重的會議資訊 JSON」（conclusions / key_points / actions，含 source_timestamp）。請將它**綜整、收斂**成一份易讀的會議記錄，嚴格輸出符合 SynthesizedMinutes schema 的 JSON。

# 綜整規則
1. 依「議題」把 conclusions / key_points 分組。每個議題輸出：title（議題標題）、summary（2–4 句討論摘要，連貫白話）、decisions（該議題的決議清單，沒有就空陣列）。
2. action_items：只列「有明確交付物」的任務。合併子步驟與重複；過程性閒聊、職人語氣、純感想**不要列**。寧少而精，不要逐句羅列。
3. 無法判定的 owner / due 一律填「未明」，priority 用 high / medium / low（可推論）。
4. 不得新增輸入 JSON 中未出現的事實或結論（延續 Fragment-First 原則）。
5. 每個 topic 與 action 帶上其依據之抽取項的 source_timestamp（放進對應的 source_timestamps）。
6. source_index：為每條 decision 與每個 action 產生一筆 {label, timestamps}，label 用「決議 N」「Action N」依輸出順序編號。
7. **不要**輸出 meta 欄位（日期/時長由系統另外填）。全程使用繁體中文。

# 公司背景
{{ background }}
```

Create `script/prompts/synthesis_user.j2`:

```jinja
以下是已抽取去重的會議資訊 JSON，請依系統指示綜整為 SynthesizedMinutes：

{{ minutes_json }}
```

Create `script/agents/synthesis_agent.py`:

```python
import json
from script.agents.base import LLMAgent
from script.schemas import MeetingMinutes, MeetingMeta, SynthesizedMinutes


class SynthesisAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="synthesis",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def synthesize(
        self, minutes: MeetingMinutes, meta: MeetingMeta
    ) -> SynthesizedMinutes:
        payload = json.dumps(minutes.model_dump(), ensure_ascii=False)
        sys = self.render("synthesis_system.j2")
        user = self.render("synthesis_user.j2", minutes_json=payload)
        result = self.call(
            system=sys, user=user, response_model=SynthesizedMinutes
        )
        result.meta = meta  # pipeline owns meta; LLM does not produce it
        return result
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_synthesis_agent.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add script/prompts/synthesis_system.j2 script/prompts/synthesis_user.j2 script/agents/synthesis_agent.py tests/test_synthesis_agent.py
git commit -m "feat: SynthesisAgent — consolidate reduced minutes into topics/actions"
```

---

### Task 4: email_writer + template

**Files:**
- Create: `script/templates/minutes_email.html.j2`
- Create: `script/email_writer.py`
- Test: `tests/test_email_writer.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_email_writer.py`:

```python
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, SourceRef, MeetingMeta,
)
from script.email_writer import write_email_html


def _synth():
    return SynthesizedMinutes(
        meta=MeetingMeta(meeting_date="2026/05/18",
                         duration_hint="逐字稿長度約 1h 55m"),
        topics=[SynthTopic(title="KPI / KTR 訂定方式",
                            summary="討論 KPI 是否納入考核。",
                            decisions=["KPI 不納入考核"],
                            source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="各團隊試算 KTR 公式",
                                  owner="各團隊", due="兩週後", priority="high",
                                  source_timestamps=["00:01:27"])],
        source_index=[SourceRef(label="決議 1", timestamps=["00:05:50"]),
                      SourceRef(label="Action 1", timestamps=["00:01:27"])],
    )


def test_email_html_has_template_fields_and_no_script(tmp_path):
    dst = tmp_path / "minutes_email.html"
    write_email_html(_synth(), str(dst), meeting_file=r"D:\m\x.txt")
    html = dst.read_text(encoding="utf-8")
    # template header fields
    assert "會議日期" in html and "2026/05/18" in html
    assert "逐字稿長度約 1h 55m" in html
    assert "參與人員" in html and "____" in html       # placeholder kept
    assert "記錄人" in html
    # §1 topic-grouped
    assert "會議記錄與決議" in html
    assert "KPI / KTR 訂定方式" in html
    assert "KPI 不納入考核" in html
    # §2 action table
    assert "Action Items" in html
    assert "<table" in html
    assert "各團隊試算 KTR 公式" in html and "兩週後" in html
    # footer source list
    assert "來源對照" in html
    assert "決議 1" in html and "00:05:50" in html
    # paste-safe: no interactivity
    assert "<script" not in html
    assert "tab(" not in html and 'class="tab"' not in html


def test_email_html_escapes_text(tmp_path):
    s = _synth()
    s.topics[0].summary = "風險 <b>注意</b> & 風控"
    dst = tmp_path / "e.html"
    write_email_html(s, str(dst), meeting_file="x")
    html = dst.read_text(encoding="utf-8")
    assert "&lt;b&gt;" in html and "&amp;" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_email_writer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'script.email_writer'`.

- [ ] **Step 3: Create the template and writer**

Create `script/templates/minutes_email.html.j2` (simple, inline-styled, table-based, **no JS/CSS classes** — pastes into Outlook cleanly):

```jinja
<div style="font-family:'Microsoft JhengHei',Arial,sans-serif;font-size:14px;color:#222;line-height:1.6;">
<p>
📅 會議日期：{{ m.meeting_date }}<br>
🕒 會議時間：____ - ____　（{{ m.duration_hint }}）<br>
📍 會議地點 / 會議室：____<br>
👥 參與人員：____<br>
📝 記錄人：____<br>
會議文件：____<br>
會議錄影：____<br>
JIRA連結 (optional)：____
</p>
<hr>
<h2 style="font-size:17px;border-bottom:2px solid #444;padding-bottom:4px;">1. 會議記錄與決議</h2>
{% for t in synth.topics %}
<h3 style="font-size:15px;margin-bottom:4px;">{{ t.title }}</h3>
<p style="margin:4px 0;">{{ t.summary }}</p>
{% if t.decisions %}
<p style="margin:4px 0;"><b>決議：</b></p>
<ul style="margin:4px 0 12px 0;">
{% for d in t.decisions %}<li>{{ d }}</li>{% endfor %}
</ul>
{% endif %}
{% endfor %}
<h2 style="font-size:17px;border-bottom:2px solid #444;padding-bottom:4px;">2. Action Items</h2>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;font-size:13px;">
<tr style="background:#f0f0f0;">
<th>#</th><th>任務</th><th>負責人</th><th>期限</th><th>優先級</th>
</tr>
{% for a in synth.action_items %}
<tr>
<td style="text-align:center;">{{ loop.index }}</td>
<td>{{ a.task }}</td>
<td>{{ a.owner }}</td>
<td>{{ a.due }}</td>
<td style="text-align:center;">{{ {'high':'高','medium':'中','low':'低'}[a.priority] }}</td>
</tr>
{% endfor %}
</table>
<hr>
<p style="font-size:12px;color:#666;"><b>來源對照</b>（逐字稿時間戳）：</p>
<ul style="font-size:12px;color:#666;">
{% for s in synth.source_index %}
<li>{{ s.label }}：{{ s.timestamps | join(', ') }}</li>
{% endfor %}
</ul>
</div>
```

Create `script/email_writer.py`:

```python
"""Simple, paste-into-Outlook email HTML for synthesized minutes.

Deliberately minimal: semantic tags + one table + inline styles, no JS,
no CSS classes, no collapsibles — so an Outlook paste keeps its layout.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

from script.schemas import SynthesizedMinutes

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def write_email_html(
    synth: SynthesizedMinutes, dst: str, *, meeting_file: str
) -> None:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        keep_trailing_newline=False,
    )
    meta = synth.meta or _empty_meta()
    html = env.get_template("minutes_email.html.j2").render(
        synth=synth, m=meta, meeting_file=meeting_file
    )
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(html, encoding="utf-8")


def _empty_meta():
    from script.schemas import MeetingMeta
    return MeetingMeta(meeting_date="YYYY/MM/DD", duration_hint="逐字稿長度未知")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_email_writer.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add script/templates/minutes_email.html.j2 script/email_writer.py tests/test_email_writer.py
git commit -m "feat: email_writer — paste-safe Outlook HTML for synthesized minutes"
```

---

### Task 5: Wire Stage 5 into pipeline + rerender reuse

**Files:**
- Modify: `script/pipeline.py`
- Modify: `tests/test_pipeline.py` (append a test)

- [ ] **Step 1: Add the failing test** — append to `tests/test_pipeline.py`:

```python
@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
def test_pipeline_runs_synthesis_stage_and_keeps_existing_outputs(
    load_m, chunk_m, MAm, RAm, SAm, write_email, write_r, write_x, tmp_path,
):
    from script.schemas import SynthesizedMinutes, SynthTopic
    settings = _settings(tmp_path)

    def _fake_load(src, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text("[00:00:00] 大家好\n[01:00:00] 結束\n", encoding="utf-8")
    load_m.side_effect = _fake_load

    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[_act()])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(
        conclusions=[_conc()], actions=[_act()],
    )
    RAm.return_value.review.return_value = ReviewResult(notes=[
        ReviewNote(target_section="conclusion", target_id="C1",
                   category="ok", severity="info", note="", suggestion=""),
        ReviewNote(target_section="action", target_id="A1",
                   category="ok", severity="info", note="", suggestion=""),
    ])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s", decisions=["d"])],
    )

    run_pipeline(_src(tmp_path), settings=settings, name="20260518_x")

    # synthesis ran on the reduced minutes
    SAm.return_value.synthesize.assert_called_once()
    sm_arg, meta_arg = SAm.return_value.synthesize.call_args.args
    assert isinstance(sm_arg, MeetingMinutes)
    assert meta_arg.meeting_date == "2026/05/18"        # inferred from name
    assert "逐字稿長度約 1h" in meta_arg.duration_hint
    # email written, and existing outputs still written (no regression)
    write_email.assert_called_once()
    write_x.assert_called_once()
    write_r.assert_called_once()
    # synthesized.json cached
    assert (Path(settings.out_dir) / "20260518_x" / "intermediate"
            / "synthesized.json").exists()


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
def test_rerender_reuses_cached_synthesized(
    write_email, write_r, write_x, tmp_path,
):
    from script.schemas import SynthesizedMinutes, SynthTopic
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    inter_dir = out_dir / "intermediate"
    inter_dir.mkdir(parents=True)
    (inter_dir / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter_dir / "review.json").write_text(
        ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    (inter_dir / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="t", summary="s")]
                           ).model_dump_json(), encoding="utf-8")

    run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)

    write_email.assert_called_once()
```

- [ ] **Step 1b: Patch the 3 existing full-flow tests (REQUIRED — they reach Stage 5)**

The pre-existing tests `test_pipeline_runs_from_transcript`, `test_pipeline_uses_cached_transcript`, and `test_pipeline_invokes_corrector_when_enabled` run the full main flow and will hit the new Stage 5. Without patching `SynthesisAgent` they would make a real LLM call. For **each** of these three tests apply this exact transformation:

1. Add a top-of-file import (once, near the other imports in `tests/test_pipeline.py`):
   `from script.schemas import SynthesizedMinutes, SynthTopic`
2. Insert these two decorator lines **immediately above the `def test_...` line** (i.e. as the innermost/bottom decorators, so their mocks become the FIRST two parameters):

```python
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.write_email_html")
```

3. Prepend the two matching params (bottom decorator → first param) to that test's signature:
   `def test_x(write_email, SAm, <existing params unchanged...>, tmp_path):`
4. Add this line in the test body, alongside the other `*.return_value` setup (before `run_pipeline(...)`):

```python
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s")]
    )
```

Do not otherwise alter those tests' existing assertions. (The `rerender` tests do not reach Stage 5's main path and need no change.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q`
Expected: FAIL — `AttributeError: <module 'script.pipeline'> does not have the attribute 'SynthesisAgent'` (and `write_email_html`). (Collection of the patched existing tests also fails until pipeline exposes those names — same root cause.)

- [ ] **Step 3: Edit `script/pipeline.py`**

(a) Add to the import block (after the existing `from script.agents.reviewer_agent import ReviewerAgent` line):

```python
from script.agents.synthesis_agent import SynthesisAgent
from script.email_writer import write_email_html
from script.meeting_meta import infer_meeting_date, duration_hint
from script.schemas import MeetingMeta
```

(b) In the `rerender_only` block, immediately **before** the `log_kv(logger, "INFO", "pipeline.done", out=str(out_dir), mode="rerender")` line, insert:

```python
        synth_path = inter_dir / "synthesized.json"
        if synth_path.exists():
            from script.schemas import SynthesizedMinutes
            synth = SynthesizedMinutes.model_validate_json(
                synth_path.read_text(encoding="utf-8")
            )
            write_email_html(
                synth, str(out_dir / "minutes_email.html"), meeting_file=src
            )
```

(c) In the main flow, locate the Stage 4 Review block. **After** the `log_kv(logger, "INFO", "stage.review", ...)` call and **before** the `# Aggregate token usage + optional cost summary` comment, insert Stage 5:

```python
    # Stage 5: synthesis -> paste-safe email HTML
    meta = MeetingMeta(
        meeting_date=infer_meeting_date(name, src),
        duration_hint=duration_hint(transcript_text),
    )
    synth_agent = SynthesisAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
    )
    usage_before_synth = len(getattr(client, "_usage_log", []))
    synth = synth_agent.synthesize(minutes, meta)
    (inter_dir / "synthesized.json").write_text(
        synth.model_dump_json(), encoding="utf-8",
    )
    write_email_html(
        synth, str(out_dir / "minutes_email.html"), meeting_file=src,
    )
    synth_usage = usage_summary(getattr(client, "_usage_log", [])[usage_before_synth:])
    log_kv(logger, "INFO", "stage.synthesis",
           topics=len(synth.topics), actions=len(synth.action_items),
           calls=synth_usage["calls"],
           tokens_in=synth_usage["prompt_tokens"],
           tokens_out=synth_usage["completion_tokens"])
```

Do not change the existing `# Outputs` block or anything else.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q`
Expected: PASS (all pipeline tests — the pre-existing ones plus the 2 new).

- [ ] **Step 5: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS — all green, 0 failures, 0 collection errors.

- [ ] **Step 6: Commit**

```bash
git add script/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline Stage 5 — synthesis + email HTML (rerender-aware)"
```

---

### Task 6: Final verification + email-render smoke

**Files:** none (verification only)

- [ ] **Step 1: Full suite green**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass, 0 errors.

- [ ] **Step 2: Import check**

Run: `.venv\Scripts\python.exe -c "import script.pipeline, script.email_writer, script.meeting_meta, script.agents.synthesis_agent; print('imports ok')"`
Expected: `imports ok`.

- [ ] **Step 3: email_writer smoke from a hand-built SynthesizedMinutes**

Run:
```
.venv\Scripts\python.exe -c "from script.schemas import *; from script.email_writer import write_email_html; s=SynthesizedMinutes(meta=MeetingMeta(meeting_date='2026/05/18',duration_hint='逐字稿長度約 1h 55m'), topics=[SynthTopic(title='KPI/KTR 訂定',summary='摘要',decisions=['KPI 不納入考核'],source_timestamps=['00:05:50'])], action_items=[SynthAction(task='各團隊試算 KTR',owner='各團隊',due='兩週後',priority='high',source_timestamps=['00:01:27'])], source_index=[SourceRef(label='決議 1',timestamps=['00:05:50'])]); write_email_html(s, r'.\_smoke_email.html', meeting_file='x'); import pathlib; t=pathlib.Path('._smoke_email.html').read_text(encoding='utf-8'); print('has table:', '<table' in t, 'no script:', '<script' not in t, 'has 決議:', '決議 1' in t)"
```
Expected: `has table: True no script: True has 決議: True`. Then delete: `Remove-Item -Force ._smoke_email.html`.

- [ ] **Step 4: (Manual, user-driven) real LLM run note**

A full real run is `python -m script.main "D:\Meeting\20260518_leadersync\5月18日 下午2-07.txt" --name leadersync_20260518 --force` (hits the company LLM; ~+1 synthesis call). After it, open `out\leadersync_20260518\minutes_email.html` and copy-paste into Outlook to confirm fidelity. This step is for the user — do not run it automatically in subagent execution.

- [ ] **Step 5: Final commit (only if any verification fixups were needed)**

```bash
git add -A && git commit -m "chore: post-synthesis verification fixups" || echo "nothing to commit"
```

---

## Notes for the implementer

- **Additive only.** Do not modify map/reduce, `minutes.html`, `review_report.md`, schemas other than appending, or any audio/speaker code. Stage 5 sits between Review and the token-aggregate block so synthesis tokens are counted in `pipeline.tokens`.
- **`git add -A` is banned** except Task 6 Step 5. Stage explicit paths (a prior refactor had `git add -A` sweep junk into a commit).
- `meta` is intentionally `None`-defaulted in the schema and assigned by the pipeline/agent after the LLM call — the LLM must not invent the meeting date.
- The email template must stay JS-free / class-free / collapsible-free; `test_email_writer.py` enforces this. If you change the template, keep those assertions passing.
- Run everything from repo root with `.venv\Scripts\python.exe`.
