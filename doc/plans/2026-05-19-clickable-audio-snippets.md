# Clickable Audio Snippets in minutes.html — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each decision and Action in the interactive `minutes.html` gets a ▶ button that plays the matching ~10s recording snippet (t−pre … t−pre+duration) from a sibling audio file copied next to the output.

**Architecture:** New `audio_assets` helper (sibling-audio discovery + timestamp→start-second math). `pipeline` copies the discovered sibling audio into `out/<name>/audio.<ext>` on full runs. `html_writer`/`minutes.html.j2` detect that file and render ▶ buttons + a single hidden `<audio>` with JS seek-and-stop. Clip window is configurable via two `.env` settings. `minutes_email.html` and the no-audio path are unchanged.

**Tech Stack:** Python, pydantic-settings, jinja2, pytest, HTML5 `<audio>` + vanilla JS.

Spec: `doc/specs/2026-05-19-clickable-audio-snippets-design.md`. Branch: `feat/email-minutes-synthesis` (continues the accumulated synthesized-minutes work). Run pytest from repo root with `.venv\Scripts\python.exe -m pytest`. `git add -A` is BANNED — stage explicit paths. Each task ends with the full suite green.

> **Sequencing:** `write_minutes_html` gains `pre`/`duration` keyword args **with defaults (5/10)**, so the existing pipeline call keeps working before Task 4 — the suite stays green at every task boundary.

---

### Task 1: audio_assets helper

**Files:**
- Create: `script/audio_assets.py`
- Test: `tests/test_audio_assets.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_audio_assets.py`:

```python
from pathlib import Path
from script.audio_assets import find_sibling_audio, clip_start


def test_find_sibling_prefers_extension_order(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    (tmp_path / "mtg.mp3").write_text("a", encoding="utf-8")
    (tmp_path / "mtg.m4a").write_text("a", encoding="utf-8")
    got = find_sibling_audio(str(tmp_path / "mtg.txt"))
    assert got is not None and got.name == "mtg.m4a"  # .m4a first in order


def test_find_sibling_single_match(tmp_path):
    (tmp_path / "會議.txt").write_text("x", encoding="utf-8")
    (tmp_path / "會議.wav").write_text("a", encoding="utf-8")
    got = find_sibling_audio(str(tmp_path / "會議.txt"))
    assert got is not None and got.name == "會議.wav"


def test_find_sibling_none_when_absent(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    assert find_sibling_audio(str(tmp_path / "mtg.txt")) is None


def test_find_sibling_ignores_different_stem(tmp_path):
    (tmp_path / "mtg.txt").write_text("x", encoding="utf-8")
    (tmp_path / "other.m4a").write_text("a", encoding="utf-8")
    assert find_sibling_audio(str(tmp_path / "mtg.txt")) is None


def test_clip_start_hhmmss_minus_pre():
    assert clip_start("01:02:03", 5) == 3723 - 5


def test_clip_start_mmss():
    assert clip_start("05:50", 5) == 350 - 5


def test_clip_start_clamps_to_zero():
    assert clip_start("00:00:02", 5) == 0


def test_clip_start_bad_value_returns_none():
    assert clip_start("", 5) is None
    assert clip_start("abc", 5) is None
    assert clip_start("1:2:3:4", 5) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_assets.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'script.audio_assets'`.

- [ ] **Step 3: Create `script/audio_assets.py`**

```python
"""Sibling-audio discovery + timestamp→clip-start math for minutes.html ▶.

The transcript's MM:SS markers come from recorder.google.com and are true
offsets into the original recording, so a sibling audio file (same folder,
same stem) can be seeked directly — no ASR/diarization involved.
"""
from pathlib import Path

_AUDIO_EXTS = (".m4a", ".mp3", ".wav", ".ogg", ".aac")


def find_sibling_audio(src: str) -> Path | None:
    """Return the same-stem audio file next to `src`, trying extensions in
    a fixed preference order; None if none exists."""
    p = Path(src)
    for ext in _AUDIO_EXTS:
        cand = p.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def clip_start(ts: str, pre: int) -> int | None:
    """`HH:MM:SS` / `MM:SS` / `SS` → start second = max(0, total - pre).

    Returns None when the timestamp cannot be parsed.
    """
    parts = (ts or "").strip().split(":")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        total = nums[0] * 3600 + nums[1] * 60 + nums[2]
    elif len(nums) == 2:
        total = nums[0] * 60 + nums[1]
    else:
        total = nums[0]
    return max(0, total - pre)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio_assets.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green (was 102; now 110).

- [ ] **Step 6: Commit**

```bash
git add script/audio_assets.py tests/test_audio_assets.py
git commit -m "feat: audio_assets — sibling-audio discovery + clip-start math"
```

---

### Task 2: Config — clip window settings

**Files:**
- Modify: `script/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add the failing test** — append to `tests/test_config.py`:

```python
def test_audio_clip_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.audio_clip_pre_seconds == 5
    assert s.audio_clip_duration_seconds == 10


def test_audio_clip_overridable(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://x.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("AUDIO_CLIP_PRE_SECONDS", "8")
    monkeypatch.setenv("AUDIO_CLIP_DURATION_SECONDS", "20")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.audio_clip_pre_seconds == 8
    assert s.audio_clip_duration_seconds == 20
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'audio_clip_pre_seconds'`.

- [ ] **Step 3: Edit `script/config.py`**

Insert this block immediately after the `# === Chunking / LLM ===` field group (after the `llm_parallel_map` line, before `# === Pricing ===`):

```python

    # === Audio clip (minutes.html ▶) ===
    audio_clip_pre_seconds: int = Field(5, alias="AUDIO_CLIP_PRE_SECONDS")
    audio_clip_duration_seconds: int = Field(10, alias="AUDIO_CLIP_DURATION_SECONDS")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -q`
Expected: PASS (all config tests incl. 2 new; `test_no_audio_settings_remain` still passes — it checks only whisper/diarization names, not `audio_clip_*`).

- [ ] **Step 5: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green (now 112).

- [ ] **Step 6: Commit**

```bash
git add script/config.py tests/test_config.py
git commit -m "feat: config AUDIO_CLIP_PRE_SECONDS / AUDIO_CLIP_DURATION_SECONDS"
```

---

### Task 3: html_writer + template — ▶ buttons & audio player

**Files:**
- Modify: `script/html_writer.py`
- Modify: `script/templates/minutes.html.j2`
- Modify: `tests/test_html_writer.py`

- [ ] **Step 1: Update `tests/test_html_writer.py`**

(a) In the existing test `test_topics_tab_renders_title_summary_decisions`, **delete the line** `assert "00:05:50" in t` (the plain-text timestamp line is removed by this task; that assertion no longer holds in the no-audio path).

(b) Append these new tests to `tests/test_html_writer.py`:

```python
def test_audio_buttons_present_when_audio_file_exists(tmp_path):
    (tmp_path / "audio.m4a").write_text("fake", encoding="utf-8")
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x", pre=5, duration=10)
    t = dst.read_text(encoding="utf-8")
    assert '<audio id="clip" src="audio.m4a"' in t
    assert 'class="play"' in t
    # topic "KPI / KTR 訂定方式" source ts 00:05:50 -> 350-5 = 345
    assert 'data-start="345"' in t
    # action "各團隊試算 KTR 公式" source ts 00:01:27 -> 87-5 = 82
    assert 'data-start="82"' in t
    assert "var CLIP_LEN=10" in t
    # the old plain-text timestamp line is gone
    assert 'class="src"' not in t


def test_no_audio_buttons_when_no_audio_file(tmp_path):
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x")
    t = dst.read_text(encoding="utf-8")
    assert '<audio' not in t
    assert 'class="play"' not in t
    assert 'class="src"' not in t


def test_audio_pre_roll_respected(tmp_path):
    (tmp_path / "audio.mp3").write_text("fake", encoding="utf-8")
    dst = tmp_path / "m.html"
    write_minutes_html(_synth(), ReviewResult(notes=[]), str(dst),
                       meeting_file="x", pre=10, duration=30)
    t = dst.read_text(encoding="utf-8")
    assert '<audio id="clip" src="audio.mp3"' in t
    assert 'data-start="340"' in t        # 350 - 10
    assert "var CLIP_LEN=30" in t
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_html_writer.py -q`
Expected: FAIL — `write_minutes_html() got an unexpected keyword argument 'pre'`.

- [ ] **Step 3: Replace `script/html_writer.py` entirely with:**

```python
"""Interactive self-contained HTML for synthesized meeting minutes.

Renders SynthesizedMinutes (topic-grouped decisions + consolidated
actions) with tab navigation, full-text search and an action priority
filter. The Review tab surfaces the reviewer's warn/error notes from the
detailed extraction pass; those reference the RAW extracted items, not the
synthesized topics, so the tab carries an on-page disclaimer.

If a sibling audio file was copied next to the output (out/<name>/audio.*),
each decision/action gets a ▶ that plays a clip around its first timestamp.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from script.schemas import SynthesizedMinutes, ReviewResult, MeetingMeta
from script.meeting_meta import empty_meta
from script.audio_assets import clip_start

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_SECTION_LABEL = {"conclusion": "結論", "key_point": "重點", "action": "Action"}
_SEV_ICON = {"info": "✅", "warn": "⚠️", "error": "❌"}


def _first_start(timestamps, pre: int):
    """clip_start of the first timestamp, or None."""
    if not timestamps:
        return None
    return clip_start(timestamps[0], pre)


def write_minutes_html(
    synth: SynthesizedMinutes,
    review: ReviewResult,
    dst: str,
    *,
    meeting_file: str,
    meta: MeetingMeta | None = None,
    pre: int = 5,
    duration: int = 10,
) -> None:
    """Render the interactive synthesized-minutes HTML.

    meta resolution order: explicit `meta` arg -> `synth.meta` -> empty_meta().
    Audio ▶ buttons appear only when an `audio.*` file sits next to `dst`.
    """
    out_dir = Path(dst).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    m = meta or synth.meta or empty_meta()

    audio_files = sorted(out_dir.glob("audio.*"))
    has_audio = bool(audio_files)
    audio_src = audio_files[0].name if has_audio else ""

    topics = [
        {
            "idx": i,
            "title": t.title,
            "summary": t.summary,
            "decisions": list(t.decisions),
            "start": _first_start(t.source_timestamps, pre),
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
            "start": _first_start(a.source_timestamps, pre),
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
        has_audio=has_audio,
        audio_src=audio_src,
        clip_len=duration,
    )
    Path(dst).write_text(html, encoding="utf-8")
```

- [ ] **Step 4: Replace `script/templates/minutes.html.j2` entirely with the content below** (write as UTF-8 via the Write tool — contains Traditional Chinese + emoji):

<<<BEGIN TEMPLATE>>>
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
    .play{margin-left:6px;border:1px solid #cbd5e0;background:#edf2f7;color:#2b6cb0;border-radius:4px;padding:0 7px;font-size:.8rem;cursor:pointer;line-height:1.6}
    .play:hover{background:#bee3f8}
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
        <ul>{% for d in t.decisions %}<li>{{ d }}{% if has_audio and t.start is not none %} <button type="button" class="play" data-start="{{ t.start }}">▶ 聽</button>{% endif %}</li>{% endfor %}</ul>
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
        <tr><th>#</th><th>任務</th><th>負責人</th><th>期限</th><th>優先級</th><th>聽</th></tr>
        {% for a in actions %}
        <tr class="searchable" data-priority="{{ a.priority }}">
          <td>{{ a.idx }}</td>
          <td>{{ a.task }}</td>
          <td>{{ a.owner }}</td>
          <td>{{ a.due }}</td>
          <td class="p-{{ a.priority }}">{{ {'high':'高','medium':'中','low':'低'}.get(a.priority, a.priority) }}</td>
          <td>{% if has_audio and a.start is not none %}<button type="button" class="play" data-start="{{ a.start }}">▶ 聽</button>{% endif %}</td>
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

  {% if has_audio %}<audio id="clip" src="{{ audio_src }}" preload="none"></audio>{% endif %}

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
      var CLIP_LEN={{ clip_len }};
      var clip=document.getElementById('clip'), stopAt=null;
      if(clip){
        clip.addEventListener('timeupdate',function(){
          if(stopAt!==null && clip.currentTime>=stopAt){ clip.pause(); stopAt=null; }
        });
        document.querySelectorAll('.play').forEach(function(btn){
          btn.addEventListener('click',function(){
            var s=+btn.dataset.start;
            clip.currentTime=s; stopAt=s+CLIP_LEN; clip.play();
          });
        });
      }
    }());
  </script>
</body>
</html>
<<<END TEMPLATE>>>

(Write exactly the content between the BEGIN/END markers, without the marker lines.)

- [ ] **Step 5: Run html_writer tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_html_writer.py -q`
Expected: PASS (all — existing adjusted + 3 new).

- [ ] **Step 6: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green. The existing `pipeline` call to `write_minutes_html` (no `pre`/`duration`) still works via the 5/10 defaults — no regression. Note exact count.

- [ ] **Step 7: Commit**

```bash
git add script/html_writer.py script/templates/minutes.html.j2 tests/test_html_writer.py
git commit -m "feat: minutes.html ▶ snippet buttons on decisions/actions (audio-aware)"
```

---

### Task 4: pipeline — copy sibling audio + pass clip settings

**Files:**
- Modify: `script/pipeline.py`
- Modify: `tests/test_pipeline.py`

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
def test_pipeline_copies_sibling_audio_and_passes_clip_kwargs(
    load_m, chunk_m, MAm, RAm, SAm, write_email, write_r, write_x, tmp_path,
):
    from script.schemas import SynthesizedMinutes, SynthTopic
    settings = _settings(tmp_path)
    # transcript src with a sibling audio next to it
    src = tmp_path / "mtg.txt"
    src.write_text("00:00\n大家好\n", encoding="utf-8")
    (tmp_path / "mtg.m4a").write_text("FAKEAUDIO", encoding="utf-8")

    def _fake_load(s, d):
        Path(d).parent.mkdir(parents=True, exist_ok=True)
        Path(d).write_text("[00:00:00] 大家好\n", encoding="utf-8")
    load_m.side_effect = _fake_load
    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[_act()])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(
        conclusions=[_conc()], actions=[_act()])
    RAm.return_value.review.return_value = ReviewResult(notes=[])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s")])

    run_pipeline(str(src), settings=settings, name="m")

    copied = Path(settings.out_dir) / "m" / "audio.m4a"
    assert copied.exists() and copied.read_text(encoding="utf-8") == "FAKEAUDIO"
    kw = write_x.call_args.kwargs
    assert kw["pre"] == 5 and kw["duration"] == 10


@patch("script.pipeline.write_minutes_html")
@patch("script.pipeline.write_review_report_md")
@patch("script.pipeline.write_email_html")
@patch("script.pipeline.SynthesisAgent")
@patch("script.pipeline.ReviewerAgent")
@patch("script.pipeline.MinutesAgent")
@patch("script.pipeline.chunk_transcript")
@patch("script.pipeline.load_transcript")
def test_pipeline_no_sibling_audio_is_not_an_error(
    load_m, chunk_m, MAm, RAm, SAm, write_email, write_r, write_x, tmp_path,
):
    from script.schemas import SynthesizedMinutes, SynthTopic
    settings = _settings(tmp_path)

    def _fake_load(s, d):
        Path(d).parent.mkdir(parents=True, exist_ok=True)
        Path(d).write_text("[00:00:00] 大家好\n", encoding="utf-8")
    load_m.side_effect = _fake_load
    chunk_m.return_value = [MagicMock(text="x", first_timestamp="00:00:00",
                                       last_timestamp="00:00:01", token_estimate=5)]
    MAm.return_value.map_chunks.return_value = [
        ChunkExtract(topics=[], conclusions=[_conc()], actions=[_act()])
    ]
    MAm.return_value.reduce.return_value = MeetingMinutes(
        conclusions=[_conc()], actions=[_act()])
    RAm.return_value.review.return_value = ReviewResult(notes=[])
    SAm.return_value.synthesize.return_value = SynthesizedMinutes(
        topics=[SynthTopic(title="t", summary="s")])

    run_pipeline(_src(tmp_path), settings=settings, name="m")  # _src has no sibling audio

    assert not (Path(settings.out_dir) / "m" / "audio.m4a").exists()
    write_x.assert_called_once()  # pipeline completed normally
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q`
Expected: FAIL — sibling audio not copied / `pre`/`duration` kwargs absent.

- [ ] **Step 3: Edit `script/pipeline.py`**

(a) Add to the import block: after `import json` add `import shutil`; and after the line `from script.meeting_meta import infer_meeting_date, duration_hint` add:
```python
from script.audio_assets import find_sibling_audio
```

(b) In the main flow, immediately BEFORE the `# Outputs` comment line (after the `# Aggregate token usage` / `pipeline.tokens` log block), insert:
```python
    # Copy sibling audio (same folder + stem as src) for minutes.html ▶
    _audio = find_sibling_audio(src)
    if _audio is not None:
        try:
            _audio_dst = out_dir / ("audio" + _audio.suffix.lower())
            shutil.copyfile(str(_audio), str(_audio_dst))
            log_kv(logger, "INFO", "stage.audio_asset", copied=str(_audio_dst))
        except OSError as e:
            log_kv(logger, "WARNING", "stage.audio_asset", error=str(e))
    else:
        log_kv(logger, "INFO", "stage.audio_asset", status="missing")
```

(c) In the `# Outputs` block, change the `write_minutes_html(...)` call to add the two kwargs:
```python
    write_minutes_html(
        synth, review, str(out_dir / "minutes.html"),
        meeting_file=src, meta=meta,
        pre=settings.audio_clip_pre_seconds,
        duration=settings.audio_clip_duration_seconds,
    )
```
Leave the following `write_review_report_md(...)` call unchanged.

(d) In the `rerender_only:` block, change its `write_minutes_html(...)` call the same way (it does NOT re-copy audio — it relies on a prior run's `out/<name>/audio.*`):
```python
        write_minutes_html(
            synth, review, str(out_dir / "minutes.html"),
            meeting_file=src, meta=synth.meta,
            pre=settings.audio_clip_pre_seconds,
            duration=settings.audio_clip_duration_seconds,
        )
```
Leave the rerender `write_review_report_md(...)` and `write_email_html(...)` calls unchanged. Do NOT add audio-copy logic to the rerender block.

- [ ] **Step 4: Run pipeline tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q`
Expected: PASS (all — existing + 2 new). Existing full-flow tests still pass: their synthetic `_src` transcript has no sibling audio, so `find_sibling_audio` returns None (no copy, `stage.audio_asset missing`), and the extra `pre`/`duration` kwargs are harmless to the `write_minutes_html` mock.

- [ ] **Step 5: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Note exact count.

- [ ] **Step 6: Commit**

```bash
git add script/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline copies sibling audio + passes clip settings to minutes.html"
```

---

### Task 5: Final verification + audio smoke

**Files:** none (verification only)

- [ ] **Step 1: Full suite green**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass, 0 errors.

- [ ] **Step 2: Import check**

Run: `.venv\Scripts\python.exe -c "import script.pipeline, script.html_writer, script.audio_assets, script.config; print('imports ok')"`
Expected: `imports ok`.

- [ ] **Step 3: Sibling-audio discovery smoke against the real meeting folder**

Run: `.venv\Scripts\python.exe -c "from script.audio_assets import find_sibling_audio, clip_start; p=find_sibling_audio(r'D:\Meeting\20260518_leadersync\5月18日 下午2-07.txt'); print('found:', p.name if p else None); print('start 00:05:50 pre5:', clip_start('00:05:50',5))"`
Expected: `found: 5月18日 下午2-07.m4a` and `start 00:05:50 pre5: 345`.

- [ ] **Step 4: Render smoke — audio-aware minutes.html from a fixture**

Run:
```
.venv\Scripts\python.exe -c "import pathlib; from script.schemas import *; from script.html_writer import write_minutes_html; d=pathlib.Path('._smoke_au'); d.mkdir(exist_ok=True); (d/'audio.m4a').write_text('x',encoding='utf-8'); s=SynthesizedMinutes(meta=MeetingMeta(meeting_date='2026/05/18',duration_hint='x'), topics=[SynthTopic(title='T',summary='S',decisions=['D1'],source_timestamps=['00:05:50'])], action_items=[SynthAction(task='A',owner='x',due='x',priority='high',source_timestamps=['00:01:27'])]); write_minutes_html(s, ReviewResult(notes=[]), str(d/'minutes.html'), meeting_file='x', pre=5, duration=10); t=(d/'minutes.html').read_text(encoding='utf-8'); print('audio tag:', '<audio id=\"clip\" src=\"audio.m4a\"' in t); print('decision play 345:', 'data-start=\"345\"' in t); print('action play 82:', 'data-start=\"82\"' in t); print('CLIP_LEN:', 'var CLIP_LEN=10' in t)"
```
Expected: all four `True`. Then clean: `Remove-Item -Recurse -Force ._smoke_au`.

- [ ] **Step 5: Final commit (only if verification fixups were needed)**

```bash
git add -A && git commit -m "chore: post-audio-snippets verification fixups" || echo "nothing to commit"
```

---

## Notes for the implementer

- **Additive / no-regression:** `minutes_email.html`, `review_report.md`, `minutes.json`, `email_writer.py`, `markdown_writer.py` must NOT change. The `pre`/`duration` defaults (5/10) on `write_minutes_html` keep every pre-Task-4 caller working, so the suite is green at each task boundary.
- The Review tab gets NO ▶ (ReviewNote has no timestamp) — by design, do not add one.
- Audio detection is by presence of `out/<name>/audio.*` next to the rendered html — this makes rerender automatically reuse a prior run's copied audio with no extra state.
- `git add -A` only in Task 5 Step 5. Stage explicit paths otherwise.
- The pre-existing untracked `scripts/probe_transcription.py` is unrelated — never stage it.
- Run everything from repo root with `.venv\Scripts\python.exe`.
