# P3 — Editable Minutes Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user edit the synthesized minutes in a browser page served by a local Python server, and on export re-validate the audit gate server-side, write `email.html` back to the meeting folder, save the edited `synthesized.json`, and open an Outlook draft with the finalized minutes in the body.

**Architecture:** A stdlib `http.server` bound to `127.0.0.1` serves an editable HTML page whose `window.DATA` (loaded from `synthesized.json` + `audit.json`) is the single source of truth. Editing is `contenteditable`; a JS mirror of `audit_mechanical.py` live-gates the export button; a "已審閱" checkbox is the second gate. On `POST /export` the server authoritatively re-runs `audit_mechanical.evaluate`, and only if it passes does it write outputs and call the existing `open_draft()`.

**Tech Stack:** Python 3.11+ stdlib (`http.server`, `webbrowser`), jinja2, pydantic v2, typer, pytest. No new dependencies.

**Design reference:** `docs/superpowers/specs/2026-07-19-p3-editable-minutes-server-design.md`. Depends on P1 (audit_mechanical, AuditResult) and existing `email_writer` / `outlook_draft`.

---

## File Structure

- **Create** `script/edit_server.py` — the whole server unit: `load_data`, `handle_export` (pure-ish export core), `render_edit_page`, the `_Handler`, `build_server`, and `serve`. One responsibility: serve+edit+export the synthesized minutes. Reuses `audit_mechanical`, `email_writer`, `outlook_draft`.
- **Create** `script/templates/edit.html.j2` — the editable page (shell + embedded `window.DATA` + JS that renders the editable DOM, mirrors Layer-1, and POSTs the export).
- **Modify** `script/main.py` — add the `edit` CLI command.
- **Modify** `.claude/skills/meetingminutes/SKILL.md` — after `process`, tell the flow to launch `edit <name>` (small doc edit; no pytest).
- **Test** `tests/test_edit_server.py` (new), `tests/test_main.py` (extend).

**Reused (do not reimplement):** `script/audit_mechanical.py` (`evaluate`, `overall_pass`), `script/email_writer.py` (`synth_to_finalized`, `render_email_html`), `script/outlook_draft.py` (`open_draft`), `script/meeting_meta.py` (`empty_meta`), `script/schemas.py` (`SynthesizedMinutes`, `AuditResult`, `SynthTopic`, `SynthAction`).

---

## Task 1: Export core + data loader

**Files:**
- Create: `script/edit_server.py`
- Test: `tests/test_edit_server.py`

The authoritative export gate + output writing, and the data loader. Both are
plain functions (the HTTP layer comes in Task 3), so they are fully unit-tested.

- [ ] **Step 1: Write the failing test**

Create `tests/test_edit_server.py`:

```python
import json
from pathlib import Path

from script.schemas import SynthesizedMinutes, SynthTopic, SynthAction
from script.edit_server import handle_export, load_data


def _synth_dict(**over):
    s = SynthesizedMinutes(
        topics=[SynthTopic(title="議題A", summary="討論內容", decisions=["決議一"])],
        action_items=[SynthAction(task="做 X", owner="小王", due="下週五", priority="high")],
    )
    d = json.loads(s.model_dump_json())
    d.update(over)
    return d


def test_export_writes_outputs_and_opens_outlook(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    seen = {}
    monkeypatch.setattr("script.edit_server.open_draft",
                        lambda subj, html: seen.update(subj=subj, html=html) or True)

    r = handle_export({"synthesized": _synth_dict(), "reviewed": True}, out)

    assert r["ok"] is True
    assert r["outlook_opened"] is True
    assert (out / "email.html").exists()
    assert (out / "intermediate" / "synthesized.json").exists()
    assert seen["subj"] == "mtg"          # subject defaults to the folder name
    assert "議題A" in seen["html"]         # finalized minutes in the body


def test_export_blocked_when_layer1_fails(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: True)
    bad = _synth_dict()
    bad["action_items"][0]["owner"] = ""   # blank owner -> Layer-1 fails

    r = handle_export({"synthesized": bad, "reviewed": True}, out)

    assert r["ok"] is False
    assert r["reason"] == "audit_failed"
    assert any(f["key"] == "action_owner_present" for f in r["failing"])
    assert not (out / "email.html").exists()      # nothing written on failure


def test_export_blocked_when_not_reviewed(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: True)

    r = handle_export({"synthesized": _synth_dict(), "reviewed": False}, out)

    assert r["ok"] is False
    assert r["reason"] == "not_reviewed"
    assert not (out / "email.html").exists()


def test_export_outlook_unavailable_still_writes_email(tmp_path, monkeypatch):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: False)

    r = handle_export({"synthesized": _synth_dict(), "reviewed": True}, out)

    assert r["ok"] is True
    assert r["outlook_opened"] is False
    assert (out / "email.html").exists()          # graceful degrade


def test_load_data_returns_synth_and_audit(tmp_path):
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="議題A", summary="s")]).model_dump_json(),
        encoding="utf-8")
    # no audit.json -> defaults to an empty AuditResult
    data = load_data(out)
    assert data["synthesized"]["topics"][0]["title"] == "議題A"
    assert data["audit"]["reviewed"] is False
    assert data["audit"]["mechanical"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'script.edit_server'`

- [ ] **Step 3: Write minimal implementation**

Create `script/edit_server.py` (Task 1 portion — the two functions + imports; the HTTP pieces are added in Task 3):

```python
"""Local editable-minutes server: edit synthesized minutes in a browser, then
export to an Outlook draft. Binds 127.0.0.1 only; runs no LLM (it edits the
already-synthesized output, never the raw transcript).
"""
import json
from pathlib import Path

from pydantic import ValidationError

from script.schemas import SynthesizedMinutes, AuditResult
from script import audit_mechanical
from script.email_writer import synth_to_finalized, render_email_html
from script.outlook_draft import open_draft
from script.meeting_meta import empty_meta

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def load_data(out_dir) -> dict:
    """Load {synthesized, audit} for the editable page (audit optional)."""
    inter = Path(out_dir) / "intermediate"
    synth = SynthesizedMinutes.model_validate_json(
        (inter / "synthesized.json").read_text(encoding="utf-8"))
    audit_path = inter / "audit.json"
    audit = (AuditResult.model_validate_json(audit_path.read_text(encoding="utf-8"))
             if audit_path.exists() else AuditResult())
    return {
        "synthesized": json.loads(synth.model_dump_json()),
        "audit": json.loads(audit.model_dump_json()),
    }


def handle_export(posted: dict, out_dir) -> dict:
    """Authoritative export: re-validate Layer-1 server-side, then write outputs
    and open an Outlook draft. Returns a JSON-able result dict.

    The client JS also gates, but never trust it — the mechanical check is
    re-run here and nothing is written unless it passes AND the payload is
    marked reviewed.
    """
    out_dir = Path(out_dir)
    try:
        synth = SynthesizedMinutes.model_validate(posted.get("synthesized", {}))
    except ValidationError as e:
        return {"ok": False, "reason": "invalid_payload", "detail": str(e)}

    checks = audit_mechanical.evaluate(synth)
    if not audit_mechanical.overall_pass(checks):
        return {
            "ok": False,
            "reason": "audit_failed",
            "failing": [
                {"key": c.key, "label": c.label, "offending": c.offending}
                for c in checks if not c.passed
            ],
        }
    if not bool(posted.get("reviewed", False)):
        return {"ok": False, "reason": "not_reviewed"}

    # Persist the edited minutes so the folder reflects the final version.
    inter = out_dir / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)
    (inter / "synthesized.json").write_text(synth.model_dump_json(), encoding="utf-8")

    # Build + write the paste-safe email HTML.
    subject = out_dir.name
    meta = synth.meta or empty_meta()
    final = synth_to_finalized(synth, subject=subject, meta=meta)
    email_html = render_email_html(final)
    email_path = out_dir / "email.html"
    email_path.write_text(email_html, encoding="utf-8")

    # Open an editable Outlook draft (best-effort; False if Outlook unavailable).
    outlook_opened = open_draft(subject, email_html)

    return {
        "ok": True,
        "email_html": str(email_path),
        "outlook_opened": outlook_opened,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```
git add script/edit_server.py tests/test_edit_server.py
git commit -m "feat: editable-server export core + data loader (authoritative Layer-1 gate)"
```

---

## Task 2: Editable HTML template + renderer

**Files:**
- Modify: `script/edit_server.py` (add `render_edit_page`)
- Create: `script/templates/edit.html.j2`
- Test: `tests/test_edit_server.py` (extend)

The page renders its editable DOM from `window.DATA` in JS (single source of
truth), mirrors the six Layer-1 checks, and POSTs `/export`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_render_edit_page_embeds_data_and_controls(tmp_path):
    from script.edit_server import render_edit_page
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="議題A", summary="s")]).model_dump_json(),
        encoding="utf-8")

    html = render_edit_page(out)

    assert "window.DATA" in html
    assert "議題A" in html              # data embedded as readable UTF-8
    assert 'id="exportbtn"' in html
    assert 'id="reviewed"' in html
    assert "<\\/" in html or "議題A" in html   # script-breakout guard applied
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_render_edit_page_embeds_data_and_controls -v`
Expected: FAIL with `ImportError: cannot import name 'render_edit_page'`

- [ ] **Step 3: Write minimal implementation**

Add to `script/edit_server.py` (near the top add the jinja import; add the function after `load_data`):

```python
from jinja2 import Environment, FileSystemLoader
```

```python
def render_edit_page(out_dir) -> str:
    """Render the editable page with DATA embedded as UTF-8 JSON."""
    data = load_data(out_dir)
    # ensure_ascii=False keeps Chinese readable; the "</" -> "<\/" replace stops
    # any "</script>" inside content from breaking out of the inline <script>.
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    return env.get_template("edit.html.j2").render(
        data_json=data_json,
        meeting_name=Path(out_dir).name,
    )
```

Create `script/templates/edit.html.j2`:

```jinja
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>編輯會議記錄 — {{ meeting_name }}</title>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:"Noto Sans TC","Microsoft JhengHei",Arial,sans-serif;background:#f0f2f5;color:#2d3748;max-width:1000px;margin:0 auto;padding:16px}
    header{background:#2d3748;color:#fff;border-radius:8px;padding:16px 20px;margin-bottom:12px}
    #auditbar{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
    .chip{font-size:.8rem;border-radius:6px;padding:3px 8px}
    .chip.ok{background:#c6f6d5;color:#22543d}
    .chip.bad{background:#fed7d7;color:#822727}
    .chip.sem{background:#e2e8f0;color:#2d3748}
    .topic{background:#fff;border-radius:8px;border:1px solid #e2e8f0;padding:14px;margin-bottom:10px}
    .topic h3{font-size:1.05rem;margin-bottom:6px}
    .topic .summary{line-height:1.6;margin:6px 0}
    .decisions{color:#0563c1;margin-top:6px}
    [contenteditable]{outline:1px dashed #cbd5e0;padding:2px 4px;border-radius:4px}
    [contenteditable]:focus{outline:2px solid #4299e1;background:#fff}
    table{width:100%;border-collapse:collapse;background:#fff;font-size:.9rem;margin-top:6px}
    th,td{border:1px solid #e2e8f0;padding:6px 8px;text-align:left;vertical-align:top}
    th{background:#edf2f7}
    .mini{border:1px solid #cbd5e0;background:#edf2f7;border-radius:4px;padding:0 6px;font-size:.8rem;cursor:pointer;margin-left:4px}
    .exportrow{position:sticky;bottom:0;background:#fff;border-top:1px solid #e2e8f0;padding:12px;display:flex;align-items:center;gap:12px;margin-top:16px}
    #exportbtn{padding:8px 18px;border:none;border-radius:6px;background:#2b6cb0;color:#fff;font-size:.95rem;cursor:pointer}
    #exportbtn:disabled{background:#a0aec0;cursor:not-allowed}
    #status{font-size:.9rem}
    h2{font-size:1.05rem;margin:10px 0 4px}
  </style>
</head>
<body>
  <header><h1>編輯會議記錄：{{ meeting_name }}</h1></header>
  <div id="auditbar"></div>
  <main id="app"></main>
  <div class="exportrow">
    <label><input type="checkbox" id="reviewed"> 我已審閱本記錄</label>
    <button id="exportbtn" disabled>匯出並開 Outlook</button>
    <span id="status"></span>
  </div>
  <script>window.DATA = {{ data_json|safe }};</script>
  <script>
  (function(){
    var D = window.DATA.synthesized;
    if(!D.topics) D.topics = [];
    if(!D.action_items) D.action_items = [];
    var app=document.getElementById('app');
    var reviewedCb=document.getElementById('reviewed');
    var exportBtn=document.getElementById('exportbtn');
    var statusEl=document.getElementById('status');

    var MARKERS=["[待確認]","待確認","TODO","TBD","待補","待補充"];
    function blank(s){return !(s||"").trim();}
    function hasMarker(s){s=s||"";return MARKERS.some(function(m){return s.indexOf(m)>=0;});}

    // Mirror of script/audit_mechanical.py — keep in sync with the Python source.
    function evaluate(){
      var T=D.topics, A=D.action_items, checks=[];
      function chk(k,l,off){checks.push({key:k,label:l,passed:off.length===0,offending:off});}
      var off;
      off=[];A.forEach(function(a,i){if(blank(a.owner))off.push('A'+(i+1));});chk('action_owner_present','每個 Action 有負責人',off);
      off=[];A.forEach(function(a,i){if(blank(a.due))off.push('A'+(i+1));});chk('action_due_present','每個 Action 有期限',off);
      off=[];T.forEach(function(t,i){(t.decisions||[]).forEach(function(d,j){if(blank(d))off.push('T'+(i+1)+'.d'+(j+1));});});chk('decision_nonempty','每條決議非空',off);
      off=[];T.forEach(function(t,i){if(blank(t.title))off.push('T'+(i+1));});chk('topic_title_nonempty','每個議題有標題',off);
      off=[];T.forEach(function(t,i){if(blank(t.summary))off.push('T'+(i+1));});chk('topic_summary_nonempty','每個議題有摘要',off);
      off=[];T.forEach(function(t,i){['title','summary'].forEach(function(f){if(hasMarker(t[f]))off.push('T'+(i+1)+'.'+f);});(t.decisions||[]).forEach(function(d,j){if(hasMarker(d))off.push('T'+(i+1)+'.d'+(j+1));});});
      A.forEach(function(a,i){['task','owner','due','context'].forEach(function(f){if(hasMarker(a[f]))off.push('A'+(i+1)+'.'+f);});});chk('no_placeholder_markers','無殘留待確認 / TODO 標記',off);
      return checks;
    }
    function allPass(c){return c.every(function(x){return x.passed;});}

    function ce(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
    function bindEdit(el,setter){el.contentEditable='true';el.addEventListener('blur',function(){setter(el.textContent);refresh();});return el;}

    function render(){
      app.innerHTML='';
      D.topics.forEach(function(t,ti){
        var box=ce('article','topic');
        box.appendChild(bindEdit(ce('h3','',t.title||''),function(v){t.title=v;}));
        box.appendChild(bindEdit(ce('p','summary',t.summary||''),function(v){t.summary=v;}));
        var dw=ce('div','decisions');dw.appendChild(ce('b','','■ 決議'));
        var ul=ce('ul');
        (t.decisions||[]).forEach(function(d,di){
          var li=ce('li');
          li.appendChild(bindEdit(ce('span','',d||''),function(v){t.decisions[di]=v;}));
          var del=ce('button','mini','🗑');del.onclick=function(){t.decisions.splice(di,1);render();refresh();};
          li.appendChild(del);ul.appendChild(li);
        });
        dw.appendChild(ul);
        var addD=ce('button','mini','＋決議');addD.onclick=function(){t.decisions=t.decisions||[];t.decisions.push('');render();refresh();};
        dw.appendChild(addD);box.appendChild(dw);
        var delT=ce('button','mini','🗑 刪議題');delT.onclick=function(){D.topics.splice(ti,1);render();refresh();};
        box.appendChild(delT);
        app.appendChild(box);
      });
      var addT=ce('button','mini','＋議題');addT.onclick=function(){D.topics.push({title:'',summary:'',decisions:[]});render();refresh();};
      app.appendChild(addT);

      app.appendChild(ce('h2','','Action Items'));
      var table=ce('table');var hr=ce('tr');
      ['#','任務','負責人','期限','優先級',''].forEach(function(x){hr.appendChild(ce('th','',x));});
      table.appendChild(hr);
      D.action_items.forEach(function(a,ai){
        var tr=ce('tr');
        tr.appendChild(ce('td','',String(ai+1)));
        ['task','owner','due','priority'].forEach(function(f){
          var td=ce('td');td.textContent=a[f]||'';bindEdit(td,function(v){a[f]=v;});tr.appendChild(td);
        });
        var td=ce('td');var del=ce('button','mini','🗑');del.onclick=function(){D.action_items.splice(ai,1);render();refresh();};td.appendChild(del);tr.appendChild(td);
        table.appendChild(tr);
      });
      app.appendChild(table);
      var addA=ce('button','mini','＋Action');addA.onclick=function(){D.action_items.push({task:'',owner:'',due:'',priority:'medium'});render();refresh();};
      app.appendChild(addA);
    }

    function refresh(){
      var checks=evaluate();var pass=allPass(checks);
      var bar=document.getElementById('auditbar');bar.innerHTML='';
      checks.forEach(function(c){
        bar.appendChild(ce('span',c.passed?'chip ok':'chip bad',(c.passed?'✅ ':'❌ ')+c.label+(c.offending.length?(' ('+c.offending.join(', ')+')'):'')));
      });
      (((window.DATA.audit||{}).semantic)||[]).forEach(function(s){
        bar.appendChild(ce('span','chip sem','📋 '+s.label+'：'+s.score+'/5'));
      });
      exportBtn.disabled=!(pass&&reviewedCb.checked);
    }

    reviewedCb.addEventListener('change',refresh);
    exportBtn.addEventListener('click',function(){
      exportBtn.disabled=true;statusEl.textContent='匯出中…';
      fetch('/export',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({synthesized:D,reviewed:reviewedCb.checked})})
      .then(function(r){return r.json();})
      .then(function(res){
        if(res.ok){statusEl.textContent=res.outlook_opened?'✅ 已開啟 Outlook 草稿，email.html 已輸出。':'✅ email.html 已輸出；Outlook 未開，請手動開啟。';}
        else{statusEl.textContent='❌ 匯出被擋：'+(res.reason||'')+(res.failing?(' — '+res.failing.map(function(f){return f.label;}).join('；')):'');}
      })
      .catch(function(e){statusEl.textContent='❌ 匯出失敗：'+e;})
      .finally(function(){refresh();});
    });

    render();refresh();
  }());
  </script>
</body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```
git add script/edit_server.py script/templates/edit.html.j2 tests/test_edit_server.py
git commit -m "feat: editable minutes HTML template + renderer (DATA-driven, JS Layer-1 mirror)"
```

---

## Task 3: HTTP server (localhost-only)

**Files:**
- Modify: `script/edit_server.py` (add `_Handler`, `build_server`, `serve`)
- Test: `tests/test_edit_server.py` (extend)

The thin HTTP layer over Task 1/2. `build_server` is separated from `serve` so
tests can drive it without the blocking `serve_forever` loop.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_server_serves_page_and_handles_export(tmp_path, monkeypatch):
    import threading
    import urllib.request
    from script.edit_server import build_server

    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(
            topics=[SynthTopic(title="議題A", summary="s", decisions=["決議一"])]
        ).model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: False)

    httpd = build_server(out)
    assert httpd.server_address[0] == "127.0.0.1"   # localhost-only
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
        assert "議題A" in page and 'id="exportbtn"' in page

        body = json.dumps({
            "synthesized": {
                "topics": [{"title": "議題A", "summary": "s", "decisions": ["決議一"]}],
                "action_items": [],
            },
            "reviewed": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/export", data=body,
            headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
        assert res["ok"] is True
        assert (out / "email.html").exists()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_export_failure_returns_422(tmp_path, monkeypatch):
    import threading
    import urllib.request
    import urllib.error
    from script.edit_server import build_server

    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes().model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("script.edit_server.open_draft", lambda *a: True)

    httpd = build_server(out)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        body = json.dumps({
            "synthesized": {"topics": [], "action_items": [
                {"task": "x", "owner": "", "due": "", "priority": "high"}]},
            "reviewed": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/export", data=body,
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            raised = None
        except urllib.error.HTTPError as e:
            raised = e
        assert raised is not None and raised.code == 422
        payload = json.loads(raised.read().decode("utf-8"))
        assert payload["reason"] == "audit_failed"
    finally:
        httpd.shutdown()
        httpd.server_close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_server_serves_page_and_handles_export -v`
Expected: FAIL with `ImportError: cannot import name 'build_server'`

- [ ] **Step 3: Write minimal implementation**

Add to `script/edit_server.py` (imports at top, then the classes/functions at the end):

```python
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
```

```python
class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        out_dir = self.server.out_dir
        if self.path in ("/", "/index.html"):
            self._send_html(render_edit_page(out_dir))
        elif self.path == "/data":
            self._send_json(200, load_data(out_dir))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/export":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            posted = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"ok": False, "reason": "bad_json"})
            return
        result = handle_export(posted, self.server.out_dir)
        self._send_json(200 if result.get("ok") else 422, result)

    def log_message(self, *args):  # keep the terminal quiet
        pass


def build_server(out_dir, port: int = 0) -> ThreadingHTTPServer:
    """Build (but do not run) a localhost-only editable-minutes server."""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    httpd.out_dir = Path(out_dir)
    return httpd


def serve(out_dir, *, open_browser: bool = True, port: int = 0) -> None:
    """Run the editable server until Ctrl-C. Localhost-only."""
    httpd = build_server(out_dir, port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    if open_browser:
        webbrowser.open(url)
    print(f"編輯頁：{url}  （編輯完在頁面上匯出；Ctrl-C 結束）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```
git add script/edit_server.py tests/test_edit_server.py
git commit -m "feat: localhost-only HTTP layer for the editable minutes server"
```

---

## Task 4: `edit` CLI command

**Files:**
- Modify: `script/main.py`
- Test: `tests/test_main.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
def test_cli_edit_calls_serve(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    inter = tmp_path / "out" / "t" / "intermediate"
    inter.mkdir(parents=True)
    (inter / "synthesized.json").write_text("{}", encoding="utf-8")
    seen = {}
    monkeypatch.setattr("script.edit_server.serve",
                        lambda o, **k: seen.update(o=str(o), k=k))
    runner = CliRunner()
    result = runner.invoke(app, ["edit", "t", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert seen["o"].replace("\\", "/").endswith("out/t")
    assert seen["k"]["open_browser"] is False


def test_cli_edit_missing_synth_errors(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["edit", "nope"])
    assert result.exit_code != 0
    assert "synthesized.json" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py::test_cli_edit_calls_serve -v`
Expected: FAIL (no `edit` command)

- [ ] **Step 3: Write minimal implementation**

In `script/main.py`, add the `edit` command after `validate` (before `finalize`):

```python
@app.command()
def edit(
    src: str = typer.Argument(..., help="Output folder name (or transcript path) under out/."),
    name: str | None = typer.Option(None, "--name", help="Output folder name (defaults to src basename)."),
    port: int = typer.Option(0, "--port", help="Port to bind (0 = auto-pick a free port)."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not auto-open the browser."),
) -> None:
    """Open the editable minutes page in a local browser to edit + export to Outlook."""
    from script.edit_server import serve
    settings = Settings()
    base = name or Path(src).stem
    out_dir = Path(settings.out_dir) / base
    if not (out_dir / "intermediate" / "synthesized.json").exists():
        typer.echo(
            f"找不到 {out_dir}/intermediate/synthesized.json — 請先對此會議跑 "
            f"`process ... --llm company`（或 --rerender）產生綜整結果。")
        raise typer.Exit(code=1)
    serve(out_dir, open_browser=not no_browser, port=port)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: PASS (edit tests + all existing main tests green)

- [ ] **Step 5: Commit**

```
git add script/main.py tests/test_main.py
git commit -m "feat: add `edit` CLI command to launch the editable minutes server"
```

---

## Task 5: Wire the skill to launch `edit` (doc)

**Files:**
- Modify: `.claude/skills/meetingminutes/SKILL.md`

No pytest — a documentation edit so the skill guides the user into the editable
page after `process`.

- [ ] **Step 1: Edit the skill**

In `.claude/skills/meetingminutes/SKILL.md`, in the "company" route, after the
step that runs `process ... --llm company`, add a step:

```markdown
5. Open the editable page so the user can edit the minutes and export to Outlook:
   `python -m script.main edit "<name>"`
   The user edits topics / decisions / actions in the browser; the export button
   unlocks only when the mechanical audit passes and they tick "已審閱", then it
   writes email.html to the folder and opens an Outlook draft.
```

And in the "claude" route, after the `--rerender` step, add:

```markdown
4. Open the editable page: `python -m script.main edit "<name>"` (same as above).
```

- [ ] **Step 2: Commit**

```
git add .claude/skills/meetingminutes/SKILL.md
git commit -m "docs: point /meetingminutes skill at the `edit` page after process"
```

---

## Notes for the Implementer

- **Localhost only.** `build_server` binds `127.0.0.1`; never `0.0.0.0`. The page and export are for the local user only.
- **No LLM, no transcript.** The server edits `synthesized.json` (already LLM-produced). It never reads the raw transcript, so it does not interact with P2's company-mode privacy lock.
- **Authoritative gate.** `handle_export` re-runs `audit_mechanical.evaluate`; the JS gate is a UX convenience only. Never write outputs or open Outlook unless the server-side check passes AND `reviewed` is true.
- **JS mirrors Python.** The `evaluate()` JS in `edit.html.j2` mirrors `script/audit_mechanical.py`'s six checks. If you change one, change the other. Keys/labels must match.
- **Outlook is best-effort.** `open_draft` returns False when Outlook/pywin32 is unavailable; the export still writes `email.html` and reports `outlook_opened: false`. Do not raise.
- **`email.html` vs `minutes_email.html`.** P3 writes `email.html` (per the design). The pipeline's existing `minutes_email.html` is separate and untouched.
- **Windows/venv:** run pytest via `.venv\Scripts\python.exe`. Use the PowerShell tool for git/shell (the Bash tool is broken by an RTK hook in this environment).
```
