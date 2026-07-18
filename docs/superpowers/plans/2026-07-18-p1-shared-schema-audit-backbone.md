# P1 — Shared Schema + Audit Backbone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a forced quality-audit stage to the Python pipeline that emits a machine-readable `intermediate/audit.json` (deterministic mechanical checks + LLM semantic checklist scores), consumed later by both engines and the editable HTML.

**Architecture:** Two-part audit. (1) A pure-Python deterministic validator computes mechanical/structural checks (Layer 1) from `SynthesizedMinutes` — no LLM, reproducible, later re-implemented in JS to block export. (2) An `AuditAgent` (LLM, same `LLMAgent` base as reviewer/synthesis) scores a fixed SOTA checklist (Layer 2). The pipeline combines both into an `AuditResult` written to `intermediate/audit.json`, in both the full run and the `--rerender` path. HTML integration is out of scope (P3).

**Tech Stack:** Python 3.11+, pydantic v2, instructor, jinja2, pytest. On-prem OpenAI-compatible endpoint (company LLM).

**Design reference:** `docs/superpowers/specs/2026-07-18-minutes-workflow-design.md` §3 (audit gate, Layers 1 & 2).

---

## File Structure

- **Create** `script/audit_mechanical.py` — pure-Python deterministic Layer-1 validator over `SynthesizedMinutes`. One responsibility: structural checks, no LLM, no I/O.
- **Create** `script/agents/audit_agent.py` — `AuditAgent(LLMAgent)`, Layer-2 semantic checklist scorer.
- **Create** `script/prompts/audit_checklist.md` — the fixed SOTA checklist (stable keys + labels), shared by Engine A prompt and Engine B.
- **Create** `script/prompts/audit_system.j2`, `script/prompts/audit_user.j2` — AuditAgent prompt templates.
- **Modify** `script/schemas.py` — add `AuditCheckMechanical`, `AuditCheckSemantic`, `SemanticAudit`, `AuditResult`.
- **Modify** `script/pipeline.py` — run audit after synthesis (full run) and rebuild/pass-through in rerender; write `intermediate/audit.json`.
- **Test** `tests/test_schemas.py`, `tests/test_audit_mechanical.py` (new), `tests/test_audit_agent.py` (new), `tests/test_pipeline.py`.

---

## Task 1: Audit schemas

**Files:**
- Modify: `script/schemas.py` (append after `FinalizedMinutes`, end of file)
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_schemas.py`:

```python
def test_audit_result_defaults_and_roundtrip():
    from script.schemas import (
        AuditCheckMechanical, AuditCheckSemantic, AuditResult,
    )
    r = AuditResult(
        mechanical=[AuditCheckMechanical(
            key="action_owner_present", label="每個 Action 有負責人",
            passed=False, offending=["A3"])],
        semantic=[AuditCheckSemantic(
            key="fluency", label="語句通順", score=4, rationale="大致通順")],
    )
    # defaults
    assert r.overall_pass is False
    assert r.reviewed is False
    # offending default is []
    assert AuditCheckMechanical(key="k", label="l", passed=True).offending == []
    # JSON round-trips (used to write/read intermediate/audit.json)
    back = AuditResult.model_validate_json(r.model_dump_json())
    assert back.mechanical[0].offending == ["A3"]
    assert back.semantic[0].score == 4


def test_semantic_audit_is_llm_response_model():
    from script.schemas import SemanticAudit, AuditCheckSemantic
    s = SemanticAudit(checks=[AuditCheckSemantic(
        key="traceable", label="可追溯", score=5, rationale="每條決議都有依據")])
    assert s.checks[0].key == "traceable"
    assert SemanticAudit().checks == []  # empty default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schemas.py::test_audit_result_defaults_and_roundtrip -v`
Expected: FAIL with `ImportError: cannot import name 'AuditResult'`

- [ ] **Step 3: Write minimal implementation**

Append to `script/schemas.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: PASS (new tests + existing schema tests green)

- [ ] **Step 5: Commit**

```bash
git add script/schemas.py tests/test_schemas.py
git commit -m "feat: add AuditResult / mechanical + semantic check schemas"
```

---

## Task 2: Pure-Python mechanical validator (Layer 1)

**Files:**
- Create: `script/audit_mechanical.py`
- Test: `tests/test_audit_mechanical.py`

The validator is deterministic and LLM-free so it is reproducible and can be
re-implemented byte-identically in JS (P3) to block export live.

- [ ] **Step 1: Write the failing test**

Create `tests/test_audit_mechanical.py`:

```python
from script.schemas import SynthesizedMinutes, SynthTopic, SynthAction
from script.audit_mechanical import evaluate, overall_pass


def _good():
    return SynthesizedMinutes(
        topics=[SynthTopic(title="KPI 制度", summary="討論 KPI 是否納入考核。",
                            decisions=["KPI 不納入年度考核"])],
        action_items=[SynthAction(task="試算 KTR 影響", owner="小王",
                                  due="下週五", priority="high")],
    )


def test_good_minutes_all_pass():
    checks = evaluate(_good())
    keys = {c.key for c in checks}
    assert keys == {
        "action_owner_present", "action_due_present", "decision_nonempty",
        "topic_title_nonempty", "topic_summary_nonempty", "no_placeholder_markers",
    }
    assert all(c.passed for c in checks)
    assert overall_pass(checks) is True


def test_blank_owner_and_due_flag_offending_action_ids():
    s = _good()
    s.action_items[0].owner = "   "
    s.action_items[0].due = ""
    checks = {c.key: c for c in evaluate(s)}
    assert checks["action_owner_present"].passed is False
    assert checks["action_owner_present"].offending == ["A1"]
    assert checks["action_due_present"].passed is False
    assert checks["action_due_present"].offending == ["A1"]
    assert overall_pass(evaluate(s)) is False


def test_blank_decision_flagged_with_dotted_id():
    s = _good()
    s.topics[0].decisions = ["有效決議", "  "]
    checks = {c.key: c for c in evaluate(s)}
    assert checks["decision_nonempty"].passed is False
    assert checks["decision_nonempty"].offending == ["T1.d2"]


def test_blank_title_and_summary_flagged():
    s = _good()
    s.topics[0].title = ""
    s.topics[0].summary = "   "
    checks = {c.key: c for c in evaluate(s)}
    assert checks["topic_title_nonempty"].offending == ["T1"]
    assert checks["topic_summary_nonempty"].offending == ["T1"]


def test_placeholder_markers_detected_across_fields():
    s = _good()
    s.topics[0].summary = "討論 KPI [待確認] 細節"
    s.action_items[0].task = "完成 TODO 的規格"
    checks = {c.key: c for c in evaluate(s)}
    c = checks["no_placeholder_markers"]
    assert c.passed is False
    assert "T1.summary" in c.offending
    assert "A1.task" in c.offending
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audit_mechanical.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.audit_mechanical'`

- [ ] **Step 3: Write minimal implementation**

Create `script/audit_mechanical.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_audit_mechanical.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add script/audit_mechanical.py tests/test_audit_mechanical.py
git commit -m "feat: deterministic Layer-1 mechanical audit validator"
```

---

## Task 3: Fixed SOTA checklist + audit prompts

**Files:**
- Create: `script/prompts/audit_checklist.md`
- Create: `script/prompts/audit_system.j2`
- Create: `script/prompts/audit_user.j2`

The checklist file is the single shared source (Engine A prompt + Engine B).
Each item has a stable `key` matching the `AuditCheckSemantic.key` the LLM must
return, plus a human `label`.

- [ ] **Step 1: Create the checklist file**

Create `script/prompts/audit_checklist.md`:

```markdown
# 會議記錄品質稽核 Checklist（Layer 2 — 語意）

依「state-of-the-art 專業會議記錄」標準，逐項評分 1–5（5 最佳）並附一句理由。
輸出的每一項 `key` 必須與下列完全一致。

- key: `traceable`
  label: 決議與討論可追溯、無臆測
  說明：每條決議/摘要都能對應到會議中實際發生的討論，沒有無中生有的內容。

- key: `fluency`
  label: 語句通順、無口語贅字
  說明：摘要為連貫書面語，去除「呃、然後、就是說」等口語與逐字稿雜訊。

- key: `actionable`
  label: 行動項具體可執行
  說明：每條 Action 以動詞開頭、含交付物與可驗收標準，非模糊的「討論一下」。

- key: `coverage`
  label: 議題涵蓋完整、無遺漏重大討論
  說明：會議中的重要討論主題都被納入某個議題，沒有明顯遺漏。

- key: `terminology`
  label: 用詞一致（人名 / 專有名詞）
  說明：同一人名、專案名、技術詞在全文用法一致，無簡繁混雜。
```

- [ ] **Step 2: Create the system prompt**

Create `script/prompts/audit_system.j2`:

```jinja
你是一位專業會議記錄品質稽核員。輸入是一份「已綜整的會議記錄 JSON」（SynthesizedMinutes：topics / action_items）。請依 checklist 逐項評分，嚴格輸出符合 SemanticAudit schema 的 JSON（欄位 checks，每項含 key / label / score / rationale）。

# 規則
- 全程使用**台灣繁體中文**，英文技術詞保留原文。
- 每個 checklist 項目都要輸出一筆，`key` 必須與 checklist 給定的完全一致，不得新增或漏項。
- `score` 為 1–5 的整數（5 = 完全符合，1 = 嚴重不符）。
- `rationale` 一句話說明評分依據，指出具體問題或亮點。
- 只評分、不改寫內容。不得捏造輸入 JSON 沒有的事實。

# 公司背景
{{ background }}
```

- [ ] **Step 3: Create the user prompt**

Create `script/prompts/audit_user.j2`:

```jinja
以下是本次稽核的 checklist：

{{ checklist }}

---

以下是已綜整的會議記錄 JSON，請依 checklist 逐項評分為 SemanticAudit：

{{ synth_json }}
```

- [ ] **Step 4: Commit**

```bash
git add script/prompts/audit_checklist.md script/prompts/audit_system.j2 script/prompts/audit_user.j2
git commit -m "feat: fixed SOTA audit checklist + AuditAgent prompts"
```

---

## Task 4: AuditAgent (Layer 2 semantic scorer)

**Files:**
- Create: `script/agents/audit_agent.py`
- Test: `tests/test_audit_agent.py`

Mirrors `SynthesisAgent`/`ReviewerAgent`: extends `LLMAgent`, renders
system+user prompts, calls the LLM with `SemanticAudit` as the response model.
It loads the shared checklist file and injects it into the user prompt.

- [ ] **Step 1: Write the failing test**

Create `tests/test_audit_agent.py`:

```python
from unittest.mock import MagicMock, patch
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction,
    SemanticAudit, AuditCheckSemantic,
)
from script.agents.audit_agent import AuditAgent


def _make_agent():
    with patch("script.agents.audit_agent.LLMAgent.__init__", return_value=None):
        a = AuditAgent.__new__(AuditAgent)
        a.render = MagicMock(side_effect=lambda tpl, **ctx: f"R({tpl})")
        a.call = MagicMock()
        a._load_checklist = MagicMock(return_value="CHECKLIST-TEXT")
        return a


def _synth():
    return SynthesizedMinutes(
        topics=[SynthTopic(title="KPI", summary="s", decisions=["d"])],
        action_items=[SynthAction(task="t", owner="o", due="d", priority="high")],
    )


def test_audit_passes_checklist_and_synth_json_to_prompt():
    a = _make_agent()
    a.call.return_value = SemanticAudit(checks=[
        AuditCheckSemantic(key="fluency", label="語句通順", score=4, rationale="ok")])

    out = a.audit(_synth())

    assert isinstance(out, list)
    assert out[0].key == "fluency"
    user_ctx = a.render.call_args_list[1].kwargs
    assert user_ctx["checklist"] == "CHECKLIST-TEXT"
    assert "KPI" in user_ctx["synth_json"]
    assert a.call.call_args.kwargs["response_model"] is SemanticAudit


def test_audit_returns_empty_list_when_llm_returns_no_checks():
    a = _make_agent()
    a.call.return_value = SemanticAudit(checks=[])
    assert a.audit(_synth()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audit_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.agents.audit_agent'`

- [ ] **Step 3: Write minimal implementation**

Create `script/agents/audit_agent.py`:

```python
import json
from pathlib import Path

from script.agents.base import LLMAgent
from script.schemas import SynthesizedMinutes, SemanticAudit, AuditCheckSemantic


class AuditAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str,
                 temperature: float = 0.2):
        super().__init__(
            name="audit",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
            temperature=temperature,
        )

    def _load_checklist(self) -> str:
        """Read the shared SOTA checklist (also used by Engine B)."""
        return (self.prompts_dir / "audit_checklist.md").read_text(encoding="utf-8")

    def audit(self, synth: SynthesizedMinutes) -> list[AuditCheckSemantic]:
        # Score only the synthesized output (what the reader sees); no raw
        # transcript — keeps the audit prompt aligned with the reader's view.
        payload = {
            "topics": [t.model_dump() for t in synth.topics],
            "action_items": [a.model_dump() for a in synth.action_items],
        }
        sys = self.render("audit_system.j2")
        user = self.render(
            "audit_user.j2",
            checklist=self._load_checklist(),
            synth_json=json.dumps(payload, ensure_ascii=False),
        )
        result = self.call(system=sys, user=user, response_model=SemanticAudit)
        return list(result.checks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_audit_agent.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add script/agents/audit_agent.py tests/test_audit_agent.py
git commit -m "feat: AuditAgent — LLM semantic checklist scorer"
```

---

## Task 5: Wire audit into the pipeline full run

**Files:**
- Modify: `script/pipeline.py` (imports; after the synthesis stage, before audio copy)
- Modify: `tests/test_pipeline.py` (existing full-run tests must patch `AuditAgent`)

The audit stage is mandatory (design §3 "強制觸發"): it always runs on a full
pipeline. It computes mechanical checks (Python) + semantic scores (LLM) and
writes `intermediate/audit.json`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`:

```python
@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
@patch("script.pipeline.AuditAgent")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
def test_pipeline_writes_audit_json(
    load_m, chunk_m, MAm, RAm, SAm, AAm, write_email, write_r, write_x, tmp_path,
):
    from script.schemas import (
        SemanticAudit, AuditCheckSemantic, AuditResult,
    )
    settings = _settings(tmp_path)

    def _fake_load(s, d):
        Path(d).parent.mkdir(parents=True, exist_ok=True)
        Path(d).write_text("[00:00:00] 大家好\n", encoding="utf-8")
    load_m.side_effect = _fake_load
    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[_act()])]
    MAm.return_value.reduce.return_value = MeetingMinutes(
        conclusions=[_conc()], actions=[_act()])
    RAm.return_value.review.return_value = ReviewResult(notes=[])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s", decisions=["d"])],
        action_items=[SynthAction(task="t", owner="o", due="d", priority="high")])
    AAm.return_value.audit.return_value = [
        AuditCheckSemantic(key="fluency", label="語句通順", score=4, rationale="ok")]

    run_pipeline(_src(tmp_path), settings=settings, name="t")

    AAm.return_value.audit.assert_called_once()
    audit_path = Path(settings.out_dir) / "t" / "intermediate" / "audit.json"
    assert audit_path.exists()
    result = AuditResult.model_validate_json(audit_path.read_text(encoding="utf-8"))
    # mechanical computed deterministically (all fields present -> all pass)
    assert result.overall_pass is True
    assert {c.key for c in result.mechanical} >= {"action_owner_present"}
    # semantic carried from the (mocked) AuditAgent
    assert result.semantic[0].key == "fluency"
    assert result.reviewed is False
```

You must also add the `AuditAgent` patch decorator + parameter to **every
existing full-run test** so their mock chain still matches (they will otherwise
construct a real `AuditAgent` and hit the network). Apply to each of
`test_pipeline_runs_from_transcript`, `test_pipeline_uses_cached_transcript`,
`test_pipeline_invokes_corrector_when_enabled`,
`test_pipeline_runs_synthesis_stage_and_keeps_existing_outputs`,
`test_pipeline_copies_sibling_audio_and_passes_clip_kwargs`,
`test_pipeline_no_sibling_audio_is_not_an_error`:

1. Add `@patch("script.pipeline.AuditAgent")` immediately above `@patch("script.pipeline.SynthesisAgent")`.
2. Add the matching parameter. `unittest.mock` injects bottom-up, so a decorator placed just above `SynthesisAgent`'s patch injects its mock immediately after `SAm` in the signature. Insert `AAm` right after `SAm`.
3. After the existing `SAm.return_value.synthesize.return_value = ...` line, add:
   `AAm.return_value.audit.return_value = []`

Example for `test_pipeline_runs_synthesis_stage_and_keeps_existing_outputs` — decorators become:

```python
@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
@patch("script.pipeline.AuditAgent")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
def test_pipeline_runs_synthesis_stage_and_keeps_existing_outputs(
    load_m, chunk_m, MAm, RAm, SAm, AAm, write_email, write_r, write_x, tmp_path,
):
```

and add `AAm.return_value.audit.return_value = []` after the `SAm.return_value.synthesize.return_value = ...` block.

> Note on the two tests decorated top-down (`test_pipeline_runs_from_transcript`,
> `test_pipeline_uses_cached_transcript`, `test_pipeline_invokes_corrector_when_enabled`):
> there `SynthesisAgent`/`write_email_html` are the **top** two decorators and map to the
> **first** params (`write_email, SAm, ...`). Keep the rule: the `AuditAgent` patch line goes
> directly above the `SynthesisAgent` patch line, and its param goes directly after `SAm` in
> the signature. Match decorator order to param order exactly.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py::test_pipeline_writes_audit_json -v`
Expected: FAIL with `AttributeError: <module 'script.pipeline'> does not have the attribute 'AuditAgent'`

- [ ] **Step 3: Write minimal implementation**

In `script/pipeline.py`, add imports near the other agent imports (after line 17, the `SynthesisAgent` import):

```python
from script.agents.audit_agent import AuditAgent
from script import audit_mechanical
from script.schemas import AuditResult
```

Also extend the existing schema import line (currently
`from script.schemas import MeetingMinutes, MeetingMeta, ReviewResult, SynthesizedMinutes`)
— leave it, and rely on the new dedicated `AuditResult` import above.

Then, in the full-run path, immediately after the synthesis block that writes
`intermediate/synthesized.json` and before `heartbeat.stop()` (i.e. right after
the `log_kv(logger, "INFO", "stage.synthesis", ...)` call), insert:

```python
    # Stage 5.5: forced quality audit (design §3). Mechanical checks are
    # deterministic (Python); semantic checklist is LLM-scored. Result is
    # consumed by the editable HTML (P3) and gates export there.
    heartbeat.set_stage("audit")
    audit_agent = AuditAgent(
        prompts_dir="script/prompts", client=client,
        model=settings.openai_model, instructor_mode=mode,
        temperature=settings.llm_temperature,
    )
    mech = audit_mechanical.evaluate(synth)
    semantic = audit_agent.audit(synth)
    audit_result = AuditResult(
        mechanical=mech,
        semantic=semantic,
        overall_pass=audit_mechanical.overall_pass(mech),
        reviewed=False,
    )
    (inter_dir / "audit.json").write_text(
        audit_result.model_dump_json(), encoding="utf-8",
    )
    log_kv(logger, "INFO", "stage.audit",
           mechanical_pass=audit_result.overall_pass,
           semantic_items=len(semantic))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS (new `test_pipeline_writes_audit_json` + all existing pipeline tests green)

- [ ] **Step 5: Commit**

```bash
git add script/pipeline.py tests/test_pipeline.py
git commit -m "feat: forced audit stage writes intermediate/audit.json on full run"
```

---

## Task 6: Audit in the --rerender path

**Files:**
- Modify: `script/pipeline.py` (the `if rerender_only:` block)
- Test: `tests/test_pipeline.py`

`--rerender` is LLM-free by contract. So on rerender we **recompute mechanical**
checks fresh from the (possibly hand-edited) cached `synthesized.json`, and
**preserve cached semantic** scores from an existing `audit.json` if present
(older runs may lack it → semantic stays empty). We never call the LLM here.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
def test_rerender_recomputes_mechanical_and_keeps_cached_semantic(
    write_email, write_r, write_x, tmp_path,
):
    from script.schemas import (
        SynthesizedMinutes, SynthTopic, SynthAction,
        AuditResult, AuditCheckSemantic,
    )
    settings = _settings(tmp_path)
    inter = Path(settings.out_dir) / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(
        ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    # cached synth has a BLANK owner -> mechanical must now fail on rerender
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(
            topics=[SynthTopic(title="t", summary="s", decisions=["d"])],
            action_items=[SynthAction(task="t", owner="", due="d", priority="high")],
        ).model_dump_json(), encoding="utf-8")
    # cached audit has semantic scores that must be preserved
    (inter / "audit.json").write_text(
        AuditResult(
            semantic=[AuditCheckSemantic(key="fluency", label="語句通順",
                                         score=5, rationale="cached")],
            overall_pass=True, reviewed=True,
        ).model_dump_json(), encoding="utf-8")

    run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)

    result = AuditResult.model_validate_json(
        (inter / "audit.json").read_text(encoding="utf-8"))
    # mechanical recomputed: blank owner -> fail -> overall_pass False
    assert result.overall_pass is False
    owner_check = next(c for c in result.mechanical if c.key == "action_owner_present")
    assert owner_check.offending == ["A1"]
    # semantic preserved from cache
    assert result.semantic[0].rationale == "cached"


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
def test_rerender_without_cached_audit_writes_mechanical_only(
    write_email, write_r, write_x, tmp_path,
):
    from script.schemas import SynthesizedMinutes, SynthTopic, AuditResult
    settings = _settings(tmp_path)
    inter = Path(settings.out_dir) / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(
        ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="t", summary="s")]
                           ).model_dump_json(), encoding="utf-8")
    # no audit.json present (older run)

    run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)

    result = AuditResult.model_validate_json(
        (inter / "audit.json").read_text(encoding="utf-8"))
    assert result.semantic == []          # nothing cached, no LLM on rerender
    assert result.mechanical              # mechanical still computed
    assert result.overall_pass is True    # no actions/decisions -> nothing to fail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py::test_rerender_recomputes_mechanical_and_keeps_cached_semantic tests/test_pipeline.py::test_rerender_without_cached_audit_writes_mechanical_only -v`
Expected: FAIL — `audit.json` is not written / semantic not preserved (assertion errors / FileNotFoundError)

- [ ] **Step 3: Write minimal implementation**

In `script/pipeline.py`, inside the `if rerender_only:` block, after
`synth = SynthesizedMinutes.model_validate_json(...)` (currently line ~120) and
before the `clips = _cut_audio_clips(...)` line, insert:

```python
        # Rebuild audit deterministically (LLM-free on rerender). Mechanical
        # checks reflect any hand-edits to the cached synthesized.json; semantic
        # scores are preserved from a prior audit.json when present (older runs
        # may not have one -> semantic stays empty).
        audit_path = inter_dir / "audit.json"
        cached_semantic = []
        cached_reviewed = False
        if audit_path.exists():
            prior = AuditResult.model_validate_json(
                audit_path.read_text(encoding="utf-8"))
            cached_semantic = prior.semantic
            cached_reviewed = prior.reviewed
        mech = audit_mechanical.evaluate(synth)
        audit_result = AuditResult(
            mechanical=mech,
            semantic=cached_semantic,
            overall_pass=audit_mechanical.overall_pass(mech),
            reviewed=cached_reviewed,
        )
        audit_path.write_text(audit_result.model_dump_json(), encoding="utf-8")
        log_kv(logger, "INFO", "stage.audit",
               mechanical_pass=audit_result.overall_pass,
               semantic_items=len(cached_semantic), mode="rerender")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS (both new rerender tests + all existing pipeline tests green)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS (no regressions across the project)

- [ ] **Step 6: Commit**

```bash
git add script/pipeline.py tests/test_pipeline.py
git commit -m "feat: rebuild audit.json on --rerender (mechanical fresh, semantic cached)"
```

---

## Notes for the Implementer

- **Company LLM only.** `AuditAgent` uses the same `client` (company on-prem endpoint) as every other agent. It never touches a cloud LLM. Do not add any external API call.
- **No transcript ingestion.** The audit scores the *synthesized* output only (topics + action_items), never the raw transcript — consistent with the privacy design.
- **`reviewed` is front-end owned.** P1 always writes `reviewed=False` on a full run and preserves the cached value on rerender. The editable HTML (P3) is what flips it to `True`.
- **Checklist keys are a contract.** `audit_checklist.md` keys (`traceable`, `fluency`, `actionable`, `coverage`, `terminology`) must match what the LLM returns and what P3's UI renders. Changing a key is a breaking change across engines.
- **Windows/venv:** run pytest via the project venv (`.venv`). If `python` is not the venv interpreter, use the venv's python explicitly.
```
