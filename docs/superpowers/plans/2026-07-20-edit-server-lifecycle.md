# Edit-server Lifecycle Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the editable-minutes server self-managing — reuse a live server on start instead of spawning a duplicate, and auto-close after a successful export — so servers converge to ≤1 per meeting and 0 after export.

**Architecture:** A JSON registry sidecar (`out/<name>/.edit-server.json`) records the current server's `{pid, port, name}`. `serve()` probes it via a new `/ping` HTTP endpoint before binding: a live match is reused (browser opens to it, no new bind); otherwise a fresh server binds, writes the registry, and clears it on teardown. `do_POST` triggers `server.shutdown()` from the handler thread on export success.

**Tech Stack:** Python stdlib `http.server` (`ThreadingHTTPServer`), `urllib.request`, `threading`, `json`, `pathlib`; pytest with `monkeypatch`.

**Spec:** `docs/superpowers/specs/2026-07-20-edit-server-lifecycle-design.md`

---

## File Structure

- **Modify** `script/edit_server.py` — add registry I/O (`read_registry`, `write_registry`, `clear_registry`), the liveness probe (`existing_live_url` + `_ping_ok`), the `/ping` GET route, export auto-close in `do_POST`, and the reuse/teardown logic in `serve()`. New imports: `os`, `threading`, `urllib.request`.
- **Modify** `script/templates/edit.html.j2` — show a terminal "server closed" message when the export response carries `server_closing: true`.
- **Modify** `tests/test_edit_server.py` — add tests for every new unit.

No new files: the logic is small and cohesive with the existing server module, matching the codebase's one-module-per-server pattern.

---

## Task 1: Registry I/O helpers

**Files:**
- Modify: `script/edit_server.py` (add imports + three functions near the top, after the `_TEMPLATE_DIR` definition on line 19)
- Test: `tests/test_edit_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_registry_round_trip(tmp_path):
    from script.edit_server import read_registry, write_registry, clear_registry
    out = tmp_path / "mtg"
    out.mkdir()
    assert read_registry(out) is None                 # absent -> None
    write_registry(out, pid=4242, port=54321)
    reg = read_registry(out)
    assert reg == {"pid": 4242, "port": 54321, "name": "mtg"}
    assert (out / ".edit-server.json").exists()
    clear_registry(out)
    assert read_registry(out) is None                 # cleared -> None
    clear_registry(out)                               # idempotent, no raise


def test_registry_corrupt_reads_as_none(tmp_path):
    from script.edit_server import read_registry
    out = tmp_path / "mtg"
    out.mkdir()
    (out / ".edit-server.json").write_text("{not json", encoding="utf-8")
    assert read_registry(out) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_registry_round_trip tests/test_edit_server.py::test_registry_corrupt_reads_as_none -v`
Expected: FAIL with `ImportError: cannot import name 'read_registry'`.

- [ ] **Step 3: Write minimal implementation**

In `script/edit_server.py`, extend the import block (currently lines 5-8) to add `os`:

```python
import json
import os
import webbrowser
```

Then add, right after `_TEMPLATE_DIR = Path(__file__).parent / "templates"` (line 19):

```python
_REGISTRY_NAME = ".edit-server.json"


def read_registry(out_dir) -> dict | None:
    """Return the {pid, port, name} sidecar dict for out_dir, or None if it is
    absent or unreadable (corrupt JSON is treated as absent, never raised)."""
    p = Path(out_dir) / _REGISTRY_NAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_registry(out_dir, pid: int, port: int) -> None:
    """Record the currently-serving process for out_dir."""
    out_dir = Path(out_dir)
    (out_dir / _REGISTRY_NAME).write_text(
        json.dumps({"pid": pid, "port": port, "name": out_dir.name}),
        encoding="utf-8")


def clear_registry(out_dir) -> None:
    """Delete the registry sidecar (best-effort; missing file is fine)."""
    try:
        (Path(out_dir) / _REGISTRY_NAME).unlink()
    except OSError:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_registry_round_trip tests/test_edit_server.py::test_registry_corrupt_reads_as_none -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add script/edit_server.py tests/test_edit_server.py
git commit -m "feat: add edit-server registry sidecar I/O"
```

---

## Task 2: `/ping` identity endpoint

**Files:**
- Modify: `script/edit_server.py` — add a `/ping` branch in `_Handler.do_GET` (currently lines 116-123)
- Test: `tests/test_edit_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_ping_returns_app_and_meeting_marker(tmp_path):
    import threading
    import urllib.request
    from script.edit_server import build_server

    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="議題A", summary="s")]).model_dump_json(),
        encoding="utf-8")

    httpd = build_server(out)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        body = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/ping", timeout=2).read().decode("utf-8")
        data = json.loads(body)
        assert data == {"app": "minutes-edit", "name": "mtg"}
    finally:
        httpd.shutdown()
        httpd.server_close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_ping_returns_app_and_meeting_marker -v`
Expected: FAIL — `/ping` returns 404 (`HTTPError: 404`).

- [ ] **Step 3: Write minimal implementation**

In `script/edit_server.py`, `_Handler.do_GET` currently reads:

```python
    def do_GET(self):
        out_dir = self.server.out_dir
        if self.path in ("/", "/index.html"):
            self._send_html(render_edit_page(out_dir))
        elif self.path == "/data":
            self._send_json(200, load_data(out_dir))
        else:
            self.send_error(404)
```

Insert a `/ping` branch before the `else`:

```python
    def do_GET(self):
        out_dir = self.server.out_dir
        if self.path in ("/", "/index.html"):
            self._send_html(render_edit_page(out_dir))
        elif self.path == "/data":
            self._send_json(200, load_data(out_dir))
        elif self.path == "/ping":
            self._send_json(200, {"app": "minutes-edit", "name": Path(out_dir).name})
        else:
            self.send_error(404)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_ping_returns_app_and_meeting_marker -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add script/edit_server.py tests/test_edit_server.py
git commit -m "feat: add /ping identity endpoint to edit server"
```

---

## Task 3: `existing_live_url` liveness probe

**Files:**
- Modify: `script/edit_server.py` — add `_ping_ok` + `existing_live_url` after `clear_registry` (from Task 1); add `import urllib.request`
- Test: `tests/test_edit_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_existing_live_url_returns_url_on_matching_ping(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    edit_server.write_registry(out, pid=1, port=6001)
    monkeypatch.setattr(edit_server, "_ping_ok",
                        lambda port, name: port == 6001 and name == "mtg")
    assert edit_server.existing_live_url(out) == "http://127.0.0.1:6001/"


def test_existing_live_url_none_and_clears_when_dead(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    edit_server.write_registry(out, pid=1, port=6002)
    monkeypatch.setattr(edit_server, "_ping_ok", lambda port, name: False)  # dead / wrong
    assert edit_server.existing_live_url(out) is None
    assert edit_server.read_registry(out) is None            # stale registry cleared


def test_existing_live_url_none_when_no_registry(tmp_path):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    assert edit_server.existing_live_url(out) is None


def test_ping_ok_false_on_connection_error(monkeypatch):
    from script import edit_server
    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert edit_server._ping_ok(59999, "mtg") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -k "existing_live_url or ping_ok" -v`
Expected: FAIL with `AttributeError: module 'script.edit_server' has no attribute 'existing_live_url'`.

- [ ] **Step 3: Write minimal implementation**

In `script/edit_server.py`, add `import urllib.request` to the import block, then add after `clear_registry`:

```python
def _ping_ok(port: int, name: str) -> bool:
    """True if 127.0.0.1:port answers /ping as our server for this meeting.

    Any error (refused, timeout, wrong/garbled marker) is a clean False — an
    HTTP probe both proves liveness and confirms the port was not reused by
    some unrelated process, which a bare pid check cannot (and on Windows a
    pid check risks TerminateProcess)."""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ping", timeout=1) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return False
    return data.get("app") == "minutes-edit" and data.get("name") == name


def existing_live_url(out_dir) -> str | None:
    """Return the URL of a live server already serving out_dir, or None.

    Reads the registry; if it points at a server that answers /ping for this
    meeting, returns its URL. Otherwise deletes the stale registry and returns
    None (so the caller starts a fresh server)."""
    reg = read_registry(out_dir)
    if not reg:
        return None
    port = reg.get("port")
    name = Path(out_dir).name
    if isinstance(port, int) and _ping_ok(port, name):
        return f"http://127.0.0.1:{port}/"
    clear_registry(out_dir)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -k "existing_live_url or ping_ok" -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add script/edit_server.py tests/test_edit_server.py
git commit -m "feat: add existing_live_url reuse probe for edit server"
```

---

## Task 4: `serve()` reuse-on-start + registry lifecycle

**Files:**
- Modify: `script/edit_server.py` — rewrite `serve()` (currently lines 150-162 in the pre-change file, shifted down by earlier tasks)
- Test: `tests/test_edit_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_serve_reuses_live_server_without_binding(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    monkeypatch.setattr(edit_server, "existing_live_url",
                        lambda o: "http://127.0.0.1:7777/")
    opened = {}
    monkeypatch.setattr(edit_server.webbrowser, "open",
                        lambda u: opened.update(url=u))
    # If serve tried to bind a real server it would call build_server; fail loudly.
    monkeypatch.setattr(edit_server, "build_server",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not bind")))

    edit_server.serve(out, open_browser=True)          # returns immediately

    assert opened["url"] == "http://127.0.0.1:7777/"


def test_serve_fresh_writes_registry_during_serve_and_clears_after(tmp_path, monkeypatch):
    from script import edit_server
    out = tmp_path / "mtg"
    out.mkdir()
    monkeypatch.setattr(edit_server, "existing_live_url", lambda o: None)
    monkeypatch.setattr(edit_server.webbrowser, "open", lambda u: None)

    seen = {}

    class _FakeHttpd:
        server_address = ("127.0.0.1", 8123)
        def serve_forever(self):
            # registry must exist *while* the server is running
            seen["during"] = edit_server.read_registry(out)
        def server_close(self):
            seen["closed"] = True

    monkeypatch.setattr(edit_server, "build_server", lambda o, port=0: _FakeHttpd())

    edit_server.serve(out, open_browser=False)

    assert seen["during"] == {"pid": os.getpid(), "port": 8123, "name": "mtg"}
    assert seen["closed"] is True
    assert edit_server.read_registry(out) is None      # cleared in finally
```

Note: `import os` is already present in the test module via Task-agnostic stdlib import; if not, add `import os` at the top of `tests/test_edit_server.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -k "serve_reuses or serve_fresh" -v`
Expected: FAIL — current `serve()` neither consults `existing_live_url` nor writes the registry (reuse test binds; fresh test's `seen["during"]` is `None`).

- [ ] **Step 3: Write minimal implementation**

Replace the existing `serve()` in `script/edit_server.py`:

```python
def serve(out_dir, *, open_browser: bool = True, port: int = 0) -> None:
    """Run the editable server until Ctrl-C or a successful export. Localhost-only.

    Reuses an already-live server for this meeting instead of binding a
    duplicate; records itself in the registry while serving and clears it on
    teardown."""
    out_dir = Path(out_dir)
    existing = existing_live_url(out_dir)
    if existing:
        print(f"已有編輯 server 在跑：{existing}（重用，未開新）")
        if open_browser:
            webbrowser.open(existing)
        return

    httpd = build_server(out_dir, port)
    bound_port = httpd.server_address[1]
    url = f"http://127.0.0.1:{bound_port}/"
    write_registry(out_dir, os.getpid(), bound_port)
    if open_browser:
        webbrowser.open(url)
    print(f"編輯頁：{url}  （匯出成功後 server 自動關閉；Ctrl-C 亦可結束）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        clear_registry(out_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -k "serve_reuses or serve_fresh" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add script/edit_server.py tests/test_edit_server.py
git commit -m "feat: reuse live edit server on start; track via registry"
```

---

## Task 5: Auto-close after successful export

**Files:**
- Modify: `script/edit_server.py` — `_Handler.do_POST` (currently lines 125-137) + `import threading`
- Test: `tests/test_edit_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_export_success_auto_closes_server(tmp_path, monkeypatch):
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
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
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
        assert res["server_closing"] is True
        # the server must stop on its own shortly after a successful export
        t.join(timeout=3.0)
        assert not t.is_alive()
    finally:
        httpd.shutdown()      # no-op if already stopped
        httpd.server_close()


def test_export_failure_does_not_close_server(tmp_path, monkeypatch):
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
        except urllib.error.HTTPError as e:
            assert e.code == 422
        # server must still be alive after a blocked export
        t.join(timeout=0.5)
        assert t.is_alive()
    finally:
        httpd.shutdown()
        httpd.server_close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -k "auto_closes or does_not_close" -v`
Expected: FAIL — `test_export_success_auto_closes_server` fails on `res["server_closing"]` (KeyError) / `t.is_alive()` still True.

- [ ] **Step 3: Write minimal implementation**

Add `import threading` to the import block of `script/edit_server.py`. Then update `_Handler.do_POST` — current code:

```python
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
```

Change the tail (from `result = handle_export(...)` onward) to:

```python
        result = handle_export(posted, self.server.out_dir)
        if result.get("ok"):
            # Export succeeded (email.html written + Outlook draft opened) = the
            # meeting is done. Tell the page, flush the response, THEN shut the
            # server down from a separate thread (calling shutdown() from this
            # handler thread is safe — it is not the serve_forever thread).
            result["server_closing"] = True
        self._send_json(200 if result.get("ok") else 422, result)
        if result.get("ok"):
            threading.Thread(target=self.server.shutdown, daemon=True).start()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py -k "auto_closes or does_not_close" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add script/edit_server.py tests/test_edit_server.py
git commit -m "feat: auto-close edit server after a successful export"
```

---

## Task 6: Page message on server close

**Files:**
- Modify: `script/templates/edit.html.j2` — the `.then(function(res){...})` success branch (lines 136-139)
- Test: `tests/test_edit_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_edit_server.py`:

```python
def test_edit_page_handles_server_closing_flag(tmp_path):
    from script.edit_server import render_edit_page
    out = tmp_path / "mtg"
    (out / "intermediate").mkdir(parents=True)
    (out / "intermediate" / "synthesized.json").write_text(
        SynthesizedMinutes(topics=[SynthTopic(title="議題A", summary="s")]).model_dump_json(),
        encoding="utf-8")
    html = render_edit_page(out)
    # the page's export handler must react to the server_closing flag
    assert "server_closing" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_edit_page_handles_server_closing_flag -v`
Expected: FAIL — template has no `server_closing` reference.

- [ ] **Step 3: Write minimal implementation**

In `script/templates/edit.html.j2`, the success branch currently reads:

```javascript
        if(res.ok){statusEl.textContent=res.outlook_opened?'✅ 已開啟 Outlook 草稿，email.html 已輸出。':'✅ email.html 已輸出；Outlook 未開，請手動開啟。';}
```

Replace it with a version that appends the close notice and disables the button so a second (doomed) export is not attempted:

```javascript
        if(res.ok){
          var base=res.outlook_opened?'✅ 已開啟 Outlook 草稿，email.html 已輸出。':'✅ email.html 已輸出；Outlook 未開，請手動開啟。';
          statusEl.textContent=base+(res.server_closing?' server 已關閉，如需重新編輯請重跑 edit。':'');
          if(res.server_closing){exportBtn.disabled=true;reviewedCb.disabled=true;}
        }
```

Also, because the `.finally(function(){refresh();})` on line 141 would re-enable the export button via `refresh()` even after close, guard `refresh()` so it does not re-enable once closed. Change the `.finally` to:

```javascript
      .finally(function(){if(!exportBtn.dataset.closed){refresh();}});
```

and in the `if(res.server_closing)` block set the flag before disabling:

```javascript
          if(res.server_closing){exportBtn.dataset.closed='1';exportBtn.disabled=true;reviewedCb.disabled=true;}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edit_server.py::test_edit_page_handles_server_closing_flag -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add script/templates/edit.html.j2 tests/test_edit_server.py
git commit -m "feat: show server-closed notice on the edit page after export"
```

---

## Task 7: Full-suite regression + manual E2E verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (existing count + the new edit-server tests). Confirm no regression in `test_edit_server.py::test_server_serves_page_and_handles_export` — that test now also auto-closes on its successful export, and its `finally` `httpd.shutdown()` must remain a harmless no-op.

- [ ] **Step 2: Manual E2E — reuse**

In one terminal (ffmpeg not required for edit):
```
.venv\Scripts\python.exe -m script.main edit "20260720_工作管理改善討論"
```
In a second terminal, run the same command again. Expected: the second prints `已有編輯 server 在跑：http://127.0.0.1:<port>/（重用，未開新）` and opens the browser to the SAME port instead of binding a new one. Confirm only one python edit process for that meeting via `Get-Process python`.

- [ ] **Step 3: Manual E2E — auto-close on export**

With the server from Step 2 running, in the browser tick「我已審閱本記錄」and click匯出. Expected: Outlook draft opens (or email.html message), the page appends「server 已關閉，如需重新編輯請重跑 edit。」, and the terminal running `serve_forever` returns to the prompt. Confirm the python edit process for that meeting has exited and `out/20260720_工作管理改善討論/.edit-server.json` is gone.

- [ ] **Step 4: Commit (if any doc/notes changed)**

No code change expected here. If verification surfaced a fix, commit it with a descriptive message.

---

## Notes for the implementer

- The registry sidecar lives under `out/`, which is git-ignored — it must never be committed, and it is outside the company-mode privacy-lock folder, so it does not interact with `hooks/minutes_privacy_guard.py`.
- Do not add a global "stop all servers" command or an idle timer — both were explicitly declined in the spec's scope boundary.
- `serve()` is intentionally not unit-tested against a real `serve_forever()` (it blocks); the fake-httpd test in Task 4 covers the registry write/clear ordering, and the reuse branch is covered by mocking `existing_live_url`.
