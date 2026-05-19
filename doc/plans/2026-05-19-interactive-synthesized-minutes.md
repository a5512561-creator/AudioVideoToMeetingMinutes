# Interactive minutes.html on Synthesized Content — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `minutes.html` render the *synthesized* content (topic-grouped decisions + consolidated actions) with an interactive UI (3 tabs + search + priority filter), while `minutes_email.html` stays the paste-safe view of the same content.

**Architecture:** Rewrite `html_writer.py` + `minutes.html.j2` to consume `SynthesizedMinutes` + `ReviewResult` + `MeetingMeta` (drop the raw `MeetingMinutes`/speaker rendering — that data still lives in `minutes.json`/`review_report.md`). Hoist the `_empty_meta()` fallback into a shared `meeting_meta.empty_meta()`. Update the pipeline's output + rerender call sites and the affected tests.

**Tech Stack:** Python, pydantic, jinja2, pytest.

Spec: `doc/specs/2026-05-19-interactive-synthesized-minutes-design.md`. Branch: `feat/email-minutes-synthesis` (builds on its unmerged synthesis work). Run pytest from repo root with `.venv\Scripts\python.exe -m pytest`.

> **Sequencing note:** `write_minutes_html`'s signature changes in Task 2, which ripples into `pipeline.py` and `tests/test_pipeline.py`. Task 2 therefore changes the writer, template, its tests, the pipeline call sites, AND the pipeline tests **together** so the full suite is green at the task boundary. Task 1 (shared `empty_meta`) is independent and green on its own. `git add -A` is banned — stage explicit paths.

---

### Task 1: Shared `empty_meta()` helper

**Files:**
- Modify: `script/meeting_meta.py`
- Modify: `script/email_writer.py`
- Modify: `tests/test_meeting_meta.py`

- [ ] **Step 1: Add the failing test** — append to `tests/test_meeting_meta.py`:

```python
def test_empty_meta_placeholders():
    from script.meeting_meta import empty_meta
    from script.schemas import MeetingMeta
    m = empty_meta()
    assert isinstance(m, MeetingMeta)
    assert m.meeting_date == "YYYY/MM/DD"
    assert m.duration_hint == "逐字稿長度未知"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_meeting_meta.py -q`
Expected: FAIL — `ImportError: cannot import name 'empty_meta'`.

- [ ] **Step 3: Add `empty_meta` to `script/meeting_meta.py`**

Add this import at the top of `script/meeting_meta.py`, immediately after the existing `from pathlib import Path` line:

```python
from script.schemas import MeetingMeta
```

Append this function to the end of `script/meeting_meta.py`:

```python


def empty_meta() -> MeetingMeta:
    """Placeholder meta when nothing could be inferred."""
    return MeetingMeta(meeting_date="YYYY/MM/DD", duration_hint="逐字稿長度未知")
```

- [ ] **Step 4: Refactor `script/email_writer.py` to use it**

In `script/email_writer.py`: change the schema import line
`from script.schemas import SynthesizedMinutes`
to:
```python
from script.schemas import SynthesizedMinutes
from script.meeting_meta import empty_meta
```
Replace `meta = synth.meta or _empty_meta()` with `meta = synth.meta or empty_meta()`.
Delete the entire `_empty_meta` function (the `def _empty_meta(): ...` block at the end, including its local `from script.schemas import MeetingMeta`).

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_meeting_meta.py tests/test_email_writer.py -q`
Expected: PASS (meeting_meta incl. new test; email_writer 2 tests unchanged behavior).
Then: `.venv\Scripts\python.exe -m pytest -q` → full suite green (was 99 passed; now 100).

- [ ] **Step 6: Commit**

```bash
git add script/meeting_meta.py script/email_writer.py tests/test_meeting_meta.py
git commit -m "refactor: shared meeting_meta.empty_meta() (used by email + html writer)"
```

---

### Task 2: Rewrite html_writer + template for synthesized content; rewire pipeline

**Files:**
- Modify: `script/html_writer.py` (full rewrite of the module body)
- Modify: `script/templates/minutes.html.j2` (full rewrite)
- Modify: `tests/test_html_writer.py` (full rewrite)
- Modify: `script/pipeline.py` (Outputs call site + rerender block + remove now-unused import if any)
- Modify: `tests/test_pipeline.py` (rerender tests + drop assertions on removed kwargs)

- [ ] **Step 1: Replace `tests/test_html_writer.py` entirely with:**

```python
import re
from script.schemas import (
    SynthesizedMinutes, SynthTopic, SynthAction, SourceRef,
    MeetingMeta, ReviewNote, ReviewResult,
)
from script.html_writer import write_minutes_html


def _synth(**over):
    base = dict(
        meta=MeetingMeta(meeting_date="2026/05/18",
                         duration_hint="逐字稿長度約 1h 55m"),
        topics=[SynthTopic(title="KPI / KTR 訂定方式",
                            summary="討論 KPI 是否納入考核。",
                            decisions=["KPI 不納入考核", "兩週後帶 KTR 公式"],
                            source_timestamps=["00:05:50"])],
        action_items=[SynthAction(task="各團隊試算 KTR 公式", owner="各團隊",
                                  due="兩週後", priority="high",
                                  source_timestamps=["00:01:27"]),
                      SynthAction(task="更新 wiki", owner="未明",
                                  due="未明", priority="low",
                                  source_timestamps=["00:30:00"])],
        source_index=[SourceRef(label="決議 1", timestamps=["00:05:50"])],
    )
    base.update(over)
    return SynthesizedMinutes(**base)


def _warn(section="conclusion", tid="C2", note="語意模糊"):
    return ReviewNote(target_section=section, target_id=tid,
                      category="ambiguity", severity="warn",
                      note=note, suggestion="請確認")


def _ok():
    return ReviewNote(target_section="conclusion", target_id="C1",
                      category="ok", severity="info", note="", suggestion="")


def test_html_has_three_tabs_and_header(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[_ok()]), str(dst),
                       meeting_file=r"D:\m\x.txt",
                       meta=MeetingMeta(meeting_date="2026/05/18",
                                        duration_hint="逐字稿長度約 1h 55m"))
    t = dst.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in t
    assert 'data-tab="topics"' in t
    assert 'data-tab="actions"' in t
    assert 'data-tab="review"' in t
    assert 'data-tab="conclusions"' not in t and 'data-tab="keypoints"' not in t
    # header meta
    assert "2026/05/18" in t
    assert "逐字稿長度約 1h 55m" in t
    assert "x.txt" in t
    # counts: 1 topic / 2 decisions / 2 actions
    assert "1 議題" in t and "2 決議" in t and "2 Action" in t


def test_topics_tab_renders_title_summary_decisions(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "KPI / KTR 訂定方式" in t
    assert "討論 KPI 是否納入考核。" in t
    assert "KPI 不納入考核" in t and "兩週後帶 KTR 公式" in t
    assert "00:05:50" in t


def test_actions_tab_table_and_priority_filter(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "<table" in t
    assert "各團隊試算 KTR 公式" in t and "更新 wiki" in t
    # priority filter buttons + rows tagged with priority
    assert 'data-priority="high"' in t and 'data-priority="low"' in t
    assert "高" in t and "低" in t  # mapped labels


def test_review_tab_shows_warn_with_disclaimer(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[_ok(), _warn(note="模糊點")]),
                       str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    rev = re.search(r'<section id="review".*?</section>', t, re.DOTALL).group(0)
    assert "原始抽取項目" in rev          # ID-gap disclaimer sentence
    assert "模糊點" in rev
    assert "請確認" in rev
    # OK notes are not listed
    assert rev.count("C1") == 0


def test_no_speaker_or_source_quote_remnants(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "speaker" not in t.lower()
    assert "SPEAKER_" not in t
    assert "source_quote" not in t
    assert "來源原句" not in t


def test_meta_fallback_when_none(tmp_path):
    s = _synth(meta=None)
    dst = tmp_path / "m.html"
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "YYYY/MM/DD" in t and "逐字稿長度未知" in t


def test_html_self_contained_and_escapes(tmp_path):
    s = _synth()
    s.topics[0].summary = "風險 <b>注意</b> & 風控"
    dst = tmp_path / "m.html"
    write_minutes_html(s, ReviewResult(notes=[]), str(dst), meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert "cdn." not in t.lower() and "//unpkg" not in t
    assert "<style>" in t and "<script>" in t
    assert "&lt;b&gt;" in t and "&amp;" in t
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_html_writer.py -q`
Expected: FAIL — old `write_minutes_html` signature (positional `MeetingMinutes`, `diarization_enabled=` kwarg) is incompatible with the new calls.

- [ ] **Step 3: Replace `script/html_writer.py` entirely with:**

```python
"""Interactive self-contained HTML for synthesized meeting minutes.

Renders SynthesizedMinutes (topic-grouped decisions + consolidated
actions) with tab navigation, full-text search and an action priority
filter. The Review tab surfaces the reviewer's warn/error notes from the
detailed extraction pass; those reference the RAW extracted items, not the
synthesized topics, so the tab carries an on-page disclaimer.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from script.schemas import SynthesizedMinutes, ReviewResult, MeetingMeta
from script.meeting_meta import empty_meta

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_SECTION_LABEL = {"conclusion": "結論", "key_point": "重點", "action": "Action"}
_SEV_ICON = {"info": "✅", "warn": "⚠️", "error": "❌"}


def write_minutes_html(
    synth: SynthesizedMinutes,
    review: ReviewResult,
    dst: str,
    *,
    meeting_file: str,
    meta: MeetingMeta | None = None,
) -> None:
    """Render the interactive synthesized-minutes HTML.

    meta resolution order: explicit `meta` arg → `synth.meta` → empty_meta().
    """
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    m = meta or synth.meta or empty_meta()

    topics = [
        {
            "idx": i,
            "title": t.title,
            "summary": t.summary,
            "decisions": list(t.decisions),
            "source_timestamps": list(t.source_timestamps),
        }
        for i, t in enumerate(synth.topics, start=1)
    ]
    actions = [
        {
            "idx": i,
            "task": a.task,
            "owner": a.owner,
            "due": a.due,
            "priority": a.priority,
        }
        for i, a in enumerate(synth.action_items, start=1)
    ]
    review_rows = [
        {
            "id": n.target_id,
            "section": _SECTION_LABEL.get(n.target_section, n.target_section),
            "category": n.category,
            "severity": n.severity,
            "icon": _SEV_ICON.get(n.severity, ""),
            "note": n.note or "",
            "suggestion": n.suggestion or "",
        }
        for n in review.notes
        if n.severity in ("warn", "error")
    ]
    n_decisions = sum(len(t["decisions"]) for t in topics)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    html = env.get_template("minutes.html.j2").render(
        meeting_file=Path(meeting_file).name or meeting_file,
        meta=m,
        topics=topics,
        actions=actions,
        review_rows=review_rows,
        n_topics=len(topics),
        n_decisions=n_decisions,
        n_actions=len(actions),
        n_warns=sum(1 for n in review.notes if n.severity == "warn"),
        n_errors=sum(1 for n in review.notes if n.severity == "error"),
    )
    Path(dst).write_text(html, encoding="utf-8")
```

- [ ] **Step 4: Replace `script/templates/minutes.html.j2` entirely with:**

```jinja
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>會議記錄 — {{ meeting_file }}</title>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:"Noto Sans TC","Microsoft JhengHei",Arial,sans-serif;background:#f0f2f5;color:#2d3748;max-width:1100px;margin:0 auto;padding:16px}
    header{background:#2d3748;color:#fff;border-radius:8px;padding:20px 24px;margin-bottom:16px}
    header h1{font-size:1.6rem;margin-bottom:12px}
    .meta{display:flex;flex-wrap:wrap;gap:10px;font-size:.85rem;color:#e2e8f0}
    nav.tabs{display:flex;flex-wrap:wrap;gap:4px;background:#fff;border-radius:8px;padding:8px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
    nav.tabs button{padding:8px 16px;border:none;border-radius:6px;background:transparent;cursor:pointer;font-size:.9rem;color:#4a5568}
    nav.tabs button:hover{background:#edf2f7}
    nav.tabs button.active{background:#2d3748;color:#fff;font-weight:600}
    .filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
    .filters input{padding:8px 12px;border:1px solid #cbd5e0;border-radius:6px;font-size:.9rem;background:#fff;flex:1;min-width:200px}
    .filters input:focus{outline:2px solid #4299e1;outline-offset:-1px}
    .tab-panel{display:none}
    .tab-panel.active{display:block}
    .topic{background:#fff;border-radius:8px;border:1px solid #e2e8f0;padding:16px;margin-bottom:12px}
    .topic[hidden]{display:none!important}
    .topic h3{font-size:1.05rem;color:#2d3748;margin-bottom:6px}
    .topic .summary{line-height:1.6;margin-bottom:8px}
    .topic ul{margin:6px 0 6px 22px}
    .topic li{margin:3px 0}
    .src{font-size:.78rem;color:#718096;margin-top:6px}
    table{width:100%;border-collapse:collapse;background:#fff;font-size:.9rem}
    th,td{border:1px solid #e2e8f0;padding:8px 10px;text-align:left;vertical-align:top}
    th{background:#edf2f7}
    tr[hidden]{display:none!important}
    .pri-btns{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
    .pri-btns button{padding:6px 12px;border:1px solid #cbd5e0;border-radius:6px;background:#fff;cursor:pointer;font-size:.85rem}
    .pri-btns button.active{background:#2d3748;color:#fff;border-color:#2d3748}
    .p-high{color:#c53030;font-weight:600}
    .p-medium{color:#b7791f}
    .p-low{color:#276749}
    .disclaimer{background:#fffbea;border:1px solid #f6e05e;border-radius:6px;padding:10px 14px;font-size:.85rem;color:#7d6608;margin-bottom:12px}
    .rev{background:#fff;border-radius:8px;padding:14px 16px;margin-bottom:10px;border-left:4px solid #cbd5e0}
    .rev[hidden]{display:none!important}
    .rev.warn{border-left-color:#f6e05e}
    .rev.error{border-left-color:#fc8181}
    .rev-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;font-weight:600}
    .rev-cat{font-size:.78rem;background:#edf2f7;border-radius:4px;padding:2px 7px;font-weight:400}
    .rev-note,.rev-sug{font-size:.87rem;color:#4a5568;margin-top:3px}
    .rev-sug{color:#276749}
    .empty{color:#718096;padding:16px}
    h2{font-size:1.05rem;margin:4px 0 10px}
  </style>
</head>
<body>
  <header>
    <h1>會議記錄</h1>
    <div class="meta">
      <span>📁 {{ meeting_file }}</span>
      <span>📅 {{ meta.meeting_date }}</span>
      <span>⏱ {{ meta.duration_hint }}</span>
      <span>📊 {{ n_topics }} 議題 / {{ n_decisions }} 決議 / {{ n_actions }} Action</span>
      <span>⚠️ {{ n_warns }} warn / ❌ {{ n_errors }} error</span>
    </div>
  </header>

  <nav class="tabs" role="tablist">
    <button data-tab="topics" class="active" role="tab">議題與決議 ({{ n_topics }})</button>
    <button data-tab="actions" role="tab">Action Items ({{ n_actions }})</button>
    <button data-tab="review" role="tab">Review ({{ n_warns + n_errors }})</button>
  </nav>

  <div class="filters">
    <input type="search" id="search" placeholder="搜尋…（在目前分頁內過濾）" aria-label="搜尋">
  </div>

  <main>
    <section id="topics" class="tab-panel active" role="tabpanel">
      {% if topics %}
      {% for t in topics %}
      <article class="topic searchable">
        <h3>{{ t.title }}</h3>
        <p class="summary">{{ t.summary }}</p>
        {% if t.decisions %}
        <b>決議：</b>
        <ul>{% for d in t.decisions %}<li>{{ d }}</li>{% endfor %}</ul>
        {% endif %}
        {% if t.source_timestamps %}
        <p class="src">⏱ {{ t.source_timestamps | join(', ') }}</p>
        {% endif %}
      </article>
      {% endfor %}
      {% else %}<p class="empty">無議題</p>{% endif %}
    </section>

    <section id="actions" class="tab-panel" role="tabpanel">
      {% if actions %}
      <div class="pri-btns">
        <button data-pri="" class="active">全部</button>
        <button data-pri="high">高</button>
        <button data-pri="medium">中</button>
        <button data-pri="low">低</button>
      </div>
      <table>
        <tr><th>#</th><th>任務</th><th>負責人</th><th>期限</th><th>優先級</th></tr>
        {% for a in actions %}
        <tr class="searchable" data-priority="{{ a.priority }}">
          <td>{{ a.idx }}</td>
          <td>{{ a.task }}</td>
          <td>{{ a.owner }}</td>
          <td>{{ a.due }}</td>
          <td class="p-{{ a.priority }}">{{ {'high':'高','medium':'中','low':'低'}[a.priority] }}</td>
        </tr>
        {% endfor %}
      </table>
      {% else %}<p class="empty">無 Action 項目</p>{% endif %}
    </section>

    <section id="review" class="tab-panel" role="tabpanel">
      <div class="disclaimer">以下為詳細審查階段針對<b>原始抽取項目</b>標記的品質警示，供交叉檢查；不與上方綜整議題逐項對應。</div>
      {% if review_rows %}
      {% for n in review_rows %}
      <article class="rev {{ n.severity }} searchable">
        <div class="rev-head">{{ n.icon }} {{ n.section }} {{ n.id }} <span class="rev-cat">{{ n.category }}</span></div>
        {% if n.note %}<p class="rev-note">{{ n.note }}</p>{% endif %}
        {% if n.suggestion %}<p class="rev-sug">建議：{{ n.suggestion }}</p>{% endif %}
      </article>
      {% endfor %}
      {% else %}<p class="empty">✅ 無 warn / error 項目</p>{% endif %}
    </section>
  </main>

  <script>
    (function(){
      var tabs=document.querySelectorAll('nav.tabs button');
      var panels=document.querySelectorAll('.tab-panel');
      tabs.forEach(function(b){b.addEventListener('click',function(){
        tabs.forEach(function(x){x.classList.remove('active')});
        b.classList.add('active');
        panels.forEach(function(p){p.classList.toggle('active',p.id===b.dataset.tab)});
        applyFilters();
      })});
      var search=document.getElementById('search');
      var pri='';
      function applyFilters(){
        var q=search.value.trim().toLowerCase();
        var active=document.querySelector('.tab-panel.active');
        if(!active)return;
        active.querySelectorAll('.searchable').forEach(function(el){
          var okQ=!q||el.textContent.toLowerCase().indexOf(q)>=0;
          var okP=true;
          if(active.id==='actions'&&pri){okP=el.getAttribute('data-priority')===pri;}
          el.hidden=!(okQ&&okP);
        });
      }
      search.addEventListener('input',applyFilters);
      document.querySelectorAll('.pri-btns button').forEach(function(b){
        b.addEventListener('click',function(){
          document.querySelectorAll('.pri-btns button').forEach(function(x){x.classList.remove('active')});
          b.classList.add('active');
          pri=b.dataset.pri;
          applyFilters();
        });
      });
    }());
  </script>
</body>
</html>
```

- [ ] **Step 5: Run html_writer tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_html_writer.py -q`
Expected: PASS (7 passed).

- [ ] **Step 6: Update `script/pipeline.py` call sites**

(a) In the `# Outputs` block, replace the `write_minutes_html(...)` call (currently passing `minutes, review, ... diarization_enabled=False, speakers_detected=0, speaker_map=spk_map`) with:

```python
    write_minutes_html(
        synth, review, str(out_dir / "minutes.html"),
        meeting_file=src, meta=meta,
    )
```
Leave the immediately-following `write_review_report_md(minutes, review, ... speaker_map=spk_map)` call **unchanged**.

(b) In the `rerender_only:` block, replace everything from `if not minutes_path.exists() or not review_path.exists():` through the existing `synth_path = inter_dir / "synthesized.json"` / `if synth_path.exists(): ...` block (i.e. the whole body between loading paths and the `log_kv(... "pipeline.done" ... mode="rerender")` line) with:

```python
        synth_path = inter_dir / "synthesized.json"
        if not minutes_path.exists() or not review_path.exists() or not synth_path.exists():
            raise RuntimeError(
                "--rerender requires cached intermediate/minutes.json, "
                "intermediate/review.json and intermediate/synthesized.json "
                "from a previous full run."
            )
        minutes = MeetingMinutes.model_validate_json(minutes_path.read_text(encoding="utf-8"))
        review = ReviewResult.model_validate_json(review_path.read_text(encoding="utf-8"))
        synth = SynthesizedMinutes.model_validate_json(synth_path.read_text(encoding="utf-8"))

        write_minutes_html(
            synth, review, str(out_dir / "minutes.html"),
            meeting_file=src, meta=synth.meta,
        )
        write_review_report_md(
            minutes, review, str(out_dir / "review_report.md"),
            meeting_file=src, diarization_enabled=False,
            speakers_detected=0, speaker_map=spk_map,
        )
        write_email_html(
            synth, str(out_dir / "minutes_email.html"), meeting_file=src
        )
```

(The `minutes_path` / `review_path` variable definitions just above this block stay; `write_review_report_md` keeps its speaker args because that writer is unchanged.)

- [ ] **Step 7: Update `tests/test_pipeline.py`**

Read `tests/test_pipeline.py`. Apply these precise changes:

1. **Remove assertions on removed kwargs.** Any assertion referencing `write_x.call_args.kwargs["diarization_enabled"]`, `["speakers_detected"]`, or `["speaker_map"]` (where `write_x` is the `write_minutes_html` mock) must be deleted — those kwargs no longer exist on `write_minutes_html`. Keep `write_x.assert_called_once()` style assertions.
2. **Replace the two rerender tests** (`test_pipeline_rerender_only_skips_llm_and_uses_cached` and `test_rerender_reuses_cached_synthesized`) with these two:

```python
@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
def test_rerender_uses_all_three_caches(write_email, write_r, write_x, tmp_path):
    from script.schemas import SynthesizedMinutes, SynthTopic
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(
        ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    (inter / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="t", summary="s")]
                           ).model_dump_json(), encoding="utf-8")

    run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)

    write_x.assert_called_once()
    write_r.assert_called_once()
    write_email.assert_called_once()
    # write_minutes_html receives the synthesized object, not MeetingMinutes
    from script.schemas import SynthesizedMinutes as _SM
    assert isinstance(write_x.call_args.args[0], _SM)


def test_rerender_raises_when_synthesized_missing(tmp_path):
    settings = _settings(tmp_path)
    out_dir = Path(settings.out_dir) / "t"
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True)
    (inter / "minutes.json").write_text(
        MeetingMinutes(conclusions=[_conc()], actions=[_act()]).model_dump_json(),
        encoding="utf-8")
    (inter / "review.json").write_text(
        ReviewResult(notes=[]).model_dump_json(), encoding="utf-8")
    # synthesized.json intentionally absent
    with pytest.raises(RuntimeError, match="synthesized.json"):
        run_pipeline(_src(tmp_path), settings=settings, name="t", rerender_only=True)
```

3. Keep `test_pipeline_rerender_only_raises_without_cache` if present (no files → still raises RuntimeError; its `match="cached"` substring still appears in the new message — leave it).
4. Leave the full-flow tests' `SynthesisAgent`/`write_email_html` patching and `SAm.return_value.synthesize.return_value = SynthesizedMinutes(...)` setup intact; only the removed-kwarg assertions from rule 1 change there.

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS — all green, 0 failures, 0 collection errors. If a full-flow test still asserts a removed `write_minutes_html` kwarg, finish applying rule 1 of Step 7.

- [ ] **Step 9: Commit**

```bash
git add script/html_writer.py script/templates/minutes.html.j2 tests/test_html_writer.py script/pipeline.py tests/test_pipeline.py
git commit -m "feat: minutes.html renders synthesized content (3 tabs + search + priority filter)"
```

---

### Task 3: Final verification + rerender smoke

**Files:** none (verification only)

- [ ] **Step 1: Full suite green**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass, 0 errors.

- [ ] **Step 2: Import check**

Run: `.venv\Scripts\python.exe -c "import script.pipeline, script.html_writer, script.email_writer, script.meeting_meta; print('imports ok')"`
Expected: `imports ok`.

- [ ] **Step 3: Rerender smoke on the existing cached run (no LLM cost)**

The prior full run left `out/leadersync_20260518/intermediate/{minutes,review,synthesized}.json`. Re-render from cache:
Run: `.venv\Scripts\python.exe -m script.main "D:\Meeting\20260518_leadersync\5月18日 下午2-07.txt" --name leadersync_20260518 --rerender`
Expected: exits 0; `pipeline.done ... mode=rerender` in the log.

Then verify the regenerated `minutes.html`:
Run (PowerShell): `$t = Get-Content 'out\leadersync_20260518\minutes.html' -Raw -Encoding UTF8; "tabs:"+($t -match 'data-tab="topics"')+($t -match 'data-tab="actions"')+($t -match 'data-tab="review"'); "no speaker:"+(-not($t -match 'SPEAKER_')); "date:"+($t -match '2026/05/18'); "disclaimer:"+($t -match '原始抽取項目')`
Expected: tabs all True, no speaker True, date True, disclaimer True. Confirm `out\leadersync_20260518\minutes_email.html` is unchanged in structure (still has `<table`, no `<script`).

- [ ] **Step 4: Final commit (only if verification fixups were needed)**

```bash
git add -A && git commit -m "chore: post-interactive-minutes verification fixups" || echo "nothing to commit"
```

---

## Notes for the implementer

- **Scope:** `email_writer.py`/`minutes_email.html` behavior must NOT change (only Task 1's `_empty_meta` → shared `empty_meta` swap, behavior identical). `review_report.md` and `minutes.json` stay raw-`MeetingMinutes`-based and unchanged.
- The Review tab disclaimer text `原始抽取項目` is asserted by tests — keep it verbatim if editing the template.
- `git add -A` is banned except Task 3 Step 5. Stage explicit paths.
- Run everything from repo root with `.venv\Scripts\python.exe`.
- The pre-existing untracked `scripts/probe_transcription.py` is unrelated — do not stage or delete it.
