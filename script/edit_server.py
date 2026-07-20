"""Local editable-minutes server: edit synthesized minutes in a browser, then
export to an Outlook draft. Binds 127.0.0.1 only; runs no LLM (it edits the
already-synthesized output, never the raw transcript).
"""
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

from script.schemas import SynthesizedMinutes, AuditResult
from script import audit_mechanical
from script.email_writer import synth_to_finalized, render_email_html
from script.outlook_draft import open_draft
from script.meeting_meta import empty_meta

_TEMPLATE_DIR = Path(__file__).parent / "templates"
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


def handle_export(posted: dict, out_dir) -> dict:
    """Authoritative export: re-validate Layer-1 server-side, then write outputs
    and open an Outlook draft. Returns a JSON-able result dict.

    The client JS also gates, but never trust it — the mechanical check is
    re-run here and nothing is written unless it passes AND the payload is
    marked reviewed.
    """
    out_dir = Path(out_dir)
    if not isinstance(posted, dict):
        return {"ok": False, "reason": "invalid_payload",
                "detail": "expected a JSON object"}
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

    inter = out_dir / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)
    (inter / "synthesized.json").write_text(synth.model_dump_json(), encoding="utf-8")

    subject = out_dir.name
    meta = synth.meta if synth.meta is not None else empty_meta()
    final = synth_to_finalized(synth, subject=subject, meta=meta)
    email_html = render_email_html(final)
    email_path = out_dir / "email.html"
    email_path.write_text(email_html, encoding="utf-8")

    outlook_opened = open_draft(subject, email_html)

    return {
        "ok": True,
        "email_html": str(email_path),
        "outlook_opened": outlook_opened,
    }


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
        elif self.path == "/ping":
            self._send_json(200, {"app": "minutes-edit", "name": Path(out_dir).name})
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
