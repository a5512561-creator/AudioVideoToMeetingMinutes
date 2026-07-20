# Edit-server lifecycle management — design

**Date:** 2026-07-20
**Status:** approved (brainstorming), pending implementation plan
**Area:** `script/edit_server.py`, `script/main.py` (`edit` command)

## Problem

`python -m script.main edit "<name>"` starts a `ThreadingHTTPServer` that runs
`serve_forever()` until `Ctrl-C`. Nothing ever stops it automatically, and every
invocation binds a fresh auto-picked port. Observed consequence: after two
meeting conversions, **four** orphaned edit servers were left listening
(each meeting launched twice), and a meeting whose minutes were already exported
and emailed still had its server alive indefinitely.

Two distinct leaks:

1. **Pre-export duplicates** — launching `edit` for the same meeting twice
   spawns two servers for one meeting.
2. **Post-export lingering** — once the user exports (writes `email.html` +
   opens the Outlook draft) the job is done, yet the server keeps running.

## Goal

Make the server self-managing so it converges to **at most one live server per
meeting, and none once the meeting is exported** — without a manual stop step.

Non-goal: a global "kill every server" command, and idle/timer-based shutdown.
Those were considered and declined to keep scope tight.

## Lifecycle

```
edit <name>  ──►  server up (or REUSE if one is already live)
                       │
                  user edits in browser
                       │
                  export succeeds (email.html + Outlook draft)
                       │
                  server auto-closes ──►  no residue
```

Re-editing after export is a plain `edit <name>` again — the reuse check finds
no live server and starts a fresh one, so the round-trip cost is one command.

## Mechanism 1 — reuse on start (prevents pre-export duplicates)

**Registry file** `out/<name>/.edit-server.json` = `{"pid": int, "port": int,
"name": str}`. Lives under `out/` (already git-ignored); never written into the
transcript/audio source folder, so it is unaffected by the company-mode privacy
lock.

**`/ping` endpoint** added to the GET handler, returns
`{"app": "minutes-edit", "name": "<out_dir.name>"}`. This is the liveness +
identity probe.

**`existing_live_url(out_dir) -> str | None`**
1. Read the registry file; absent/corrupt → return `None`.
2. HTTP `GET http://127.0.0.1:<port>/ping` with a 1 s timeout.
3. If it returns JSON with `app == "minutes-edit"` **and** `name` matching this
   meeting → the server is live for this meeting → return
   `http://127.0.0.1:<port>/`.
4. Otherwise (connection refused, timeout, wrong marker, wrong name — i.e. dead
   server or a port reused by something else) → delete the stale registry file
   and return `None`.

**`serve()` change**
- Call `existing_live_url(out_dir)` first.
  - Live URL found → print a "reusing existing server" message, open the browser
    to it (when `open_browser`), and **return without binding a new server**.
  - `None` → bind the port, write the registry (`pid = os.getpid()`, the actual
    bound port, `name`), open the browser, `serve_forever()`.

### Why HTTP `/ping` instead of a pid liveness check

On Windows, `os.kill(pid, 0)` does not mean "is it alive?" — CPython maps a
non-`CTRL_*` signal to `TerminateProcess`, so it could kill the process. [LLM推論]
An HTTP ping avoids that footgun and additionally proves the port belongs to
*our* server for *this* meeting, closing the port-reuse false-positive. The
`pid` is still stored in the registry for observability and any future tooling.

## Mechanism 2 — auto-close after export (prevents post-export lingering)

- In `do_POST` handling `/export`, when `handle_export` returns success
  (`ok == True`, meaning `email.html` was written and the Outlook draft opened):
  1. Send the JSON response first (so the browser receives it), with an added
     `"server_closing": true` field.
  2. Start a short-lived `threading.Thread(target=self.server.shutdown,
     daemon=True)` to break `serve_forever()`.
- A failed export (mechanical audit not passing, or "已審閱" not ticked — the
  existing Layer-1 server-side re-validation in `handle_export`) does **not**
  close the server, so the user can fix and retry.
- The editable page, on seeing `server_closing: true` in the export response,
  shows a terminal message such as「已匯出，server 已關閉，如需重新編輯請重跑
  `edit`」.

### Shutdown-thread safety

`ThreadingHTTPServer` serves each request on its own thread, while
`serve_forever()` runs on the main thread. `shutdown()` blocks until the
`serve_forever()` loop exits and must not be called from the serving thread;
calling it from a request-handler thread (a different thread) is safe. [LLM推論]
Using a separate daemon thread also lets the current response flush before the
loop tears down.

## Teardown

`serve()` wraps `serve_forever()` in `try/finally`. The `finally` block runs on
both `Ctrl-C` and the auto-close path and performs:
- `httpd.server_close()`
- delete `out/<name>/.edit-server.json` (registry cleanup)

So the registry never outlives its server, keeping `existing_live_url` honest.

## Components / interfaces

| Unit | Signature | Responsibility |
|---|---|---|
| registry I/O | `read_registry(out_dir) -> dict \| None`, `write_registry(out_dir, pid, port)`, `clear_registry(out_dir)` | persist/read/delete the `.edit-server.json` sidecar |
| liveness probe | `existing_live_url(out_dir) -> str \| None` | decide reuse vs fresh; self-heals stale registry |
| `/ping` handler | GET route in `_Handler.do_GET` | app+meeting identity marker |
| export auto-close | logic in `_Handler.do_POST` | trigger `server.shutdown()` on export success |
| `serve()` | existing entry, modified | orchestrate reuse → serve → teardown |

## Error handling

- Corrupt/unreadable registry JSON → treat as absent (start fresh), overwrite on
  bind. Never fail the `edit` command over a bad sidecar.
- `/ping` request errors of any kind → `existing_live_url` returns `None`
  (fail toward starting a fresh server, the safe default).
- Registry deletion failing (file already gone / locked) → swallow; it is
  best-effort cleanup, not a correctness boundary.

## Testing

- `read/write/clear_registry` round-trip, including corrupt-JSON → `None`.
- `existing_live_url`: mock `urllib` to (a) return the correct marker → URL,
  (b) return wrong name/marker → `None` + registry cleared, (c) raise
  (refused/timeout) → `None` + registry cleared.
- `/ping` handler returns the expected JSON for a given `out_dir`.
- Export success path starts exactly one shutdown call (mock
  `httpd.shutdown`); export failure path starts none.
- Reuse decision is exercised as a pure function (`existing_live_url`) so no
  real `serve_forever()` is needed in tests.

## Scope boundary (accepted)

Only same-meeting duplication and post-export lingering are addressed. Two
*different* meetings still each keep one live server until their own export.
That is the intended steady state («每會議 ≤1，匯出後 0»), not unbounded growth.
A one-off cleanup of the four servers already running is a separate manual step,
not part of this mechanism.
