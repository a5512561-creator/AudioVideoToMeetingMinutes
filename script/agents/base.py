import json
import re
from dataclasses import dataclass
from pathlib import Path
import instructor
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel


@dataclass(frozen=True)
class FewShot:
    input: str
    output: str


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
# Locates a ```<lang>?\n…\n``` markdown code block anywhere in the string.
# Reasoning models put valid JSON inside fences and sometimes also prepend
# natural-language preamble ("OK, here is the consolidated output:\n\n```json…").
# We search rather than anchor at start/end so both wrap modes are recovered.
# Permissive on the language tag (json / blank / etc.) — models are inconsistent.
_FENCE_RE = re.compile(
    r"```[A-Za-z0-9]*\s*\n(.*?)\n\s*```",
    re.DOTALL,
)


def _unfence(s: str | None) -> str | None:
    """Extract the first ```lang\\n…\\n``` block's body from a tool-call
    argument or content string. Returns the input unchanged when no fence
    is present, so already-clean JSON passes through untouched."""
    if not s:
        return s
    m = _FENCE_RE.search(s)
    return m.group(1) if m else s


def _strip_thinking_tokens(client):
    """Wrap client.chat.completions.create to clean up two common OSS-reasoning-
    model artefacts and record per-call token usage.

    Cleanups applied to both ``message.content`` and every
    ``tool_call.function.arguments``:

    1. ``<think>…</think>`` blocks — gpt-oss, deepseek-r1, qwen3-thinking and
       Realtek's "medium" model sometimes leak reasoning tokens into the
       output stream where Instructor's JSON parser expects a clean payload.
    2. Triple-backtick markdown code fences — same family of reasoning
       models will, when using Instructor's ``TOOLS`` mode, place valid JSON
       inside fences as the tool-call ``arguments`` string. Pydantic then
       sees a backtick at line-1-column-1 and rejects with
       ``Invalid JSON: expected value at line 1 column 1``. Unfencing fixes
       the call without forcing a mode change.

    Side effect: each call appends a dict to ``client._usage_log`` with
    prompt_tokens / completion_tokens / total_tokens. Pipeline reads this to
    aggregate per-stage and per-pipeline token totals.

    Idempotent: a second call is a no-op.
    """
    if getattr(client, "_strip_thinking_installed", False):
        return client
    _orig = client.chat.completions.create
    if not hasattr(client, "_usage_log"):
        client._usage_log = []

    def _create(*a, **kw):
        resp = _orig(*a, **kw)
        # Capture token usage if present (some endpoints omit it on errors).
        usage = getattr(resp, "usage", None)
        if usage is not None:
            client._usage_log.append({
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            })
        # Strip thinking tokens AND markdown fences from content +
        # tool_call arguments. Order: <think> blocks first (a fenced JSON
        # could otherwise hide them), then fence unwrap on the trimmed text.
        for choice in getattr(resp, "choices", []):
            msg = getattr(choice, "message", None)
            if msg is None:
                continue
            if getattr(msg, "content", None):
                msg.content = _unfence(_THINK_RE.sub("", msg.content))
            for tc in (getattr(msg, "tool_calls", None) or []):
                fn = getattr(tc, "function", None)
                if fn and getattr(fn, "arguments", None):
                    fn.arguments = _unfence(_THINK_RE.sub("", fn.arguments))
        return resp

    client.chat.completions.create = _create
    client._strip_thinking_installed = True
    return client


def usage_summary(usage_log: list[dict]) -> dict:
    """Aggregate a list of per-call usage dicts into totals."""
    return {
        "calls": len(usage_log),
        "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage_log),
        "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage_log),
        "total_tokens": sum(u.get("total_tokens", 0) for u in usage_log),
    }


def estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    price_per_1m_input: float,
    price_per_1m_output: float,
) -> float:
    """Cost in the configured currency (zero when prices unset)."""
    return (
        prompt_tokens * price_per_1m_input
        + completion_tokens * price_per_1m_output
    ) / 1_000_000


class LLMAgent:
    def __init__(
        self,
        *,
        name: str,
        prompts_dir: str,
        client,
        model: str,
        instructor_mode: str,
    ) -> None:
        self.name = name
        self.prompts_dir = Path(prompts_dir)
        self.model = model
        client = _strip_thinking_tokens(client)
        self.llm = instructor.from_openai(
            client, mode=getattr(instructor.Mode, instructor_mode)
        )
        self.jinja = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            keep_trailing_newline=False,
            autoescape=False,
        )
        self.background = (self.prompts_dir / "background.md").read_text(encoding="utf-8")
        self.few_shots = self._load_few_shots()

    def _load_few_shots(self) -> list[FewShot]:
        d = self.prompts_dir / "few_shot" / self.name
        if not d.is_dir():
            return []
        out: list[FewShot] = []
        for path in sorted(d.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(FewShot(input=data["input"], output=data["output"]))
        return out

    def render(self, template: str, **ctx) -> str:
        ctx.setdefault("background", self.background)
        ctx.setdefault("few_shots", self.few_shots)
        return self.jinja.get_template(template).render(**ctx)

    def call(
        self,
        *,
        system: str,
        user: str,
        response_model: type[BaseModel],
        max_retries: int = 3,
    ):
        return self.llm.chat.completions.create(
            model=self.model,
            response_model=response_model,
            max_retries=max_retries,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )


def probe_instructor_mode(client, *, model: str) -> str:
    """Probe the OpenAI-compat server for tool-calling support.

    Returns one of Instructor's OpenAI-provider modes:
      - "TOOLS"  : function/tool calling works (preferred — Instructor uses it
                   for strict schema validation)
      - "JSON"   : tools rejected, fall back to response_format=json_object
                   (broadly compatible)
    """
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "probe",
                    "description": "test",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
            max_tokens=4,
        )
        return "TOOLS"
    except Exception:
        return "JSON"
