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


def _strip_thinking_tokens(client):
    """Wrap client.chat.completions.create to strip <think>...</think> blocks
    and record per-call token usage.

    Required for OSS reasoning models (gpt-oss, deepseek-r1, qwen3-thinking,
    Realtek's "medium" model) that prepend reasoning tokens to the actual JSON
    payload — Instructor's JSON parser would choke on the prefix otherwise.

    Side effect: each call appends a dict to client._usage_log with
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
        # Strip thinking tokens from content + tool_call arguments.
        for choice in getattr(resp, "choices", []):
            msg = getattr(choice, "message", None)
            if msg is None:
                continue
            if getattr(msg, "content", None):
                msg.content = _THINK_RE.sub("", msg.content)
            for tc in (getattr(msg, "tool_calls", None) or []):
                fn = getattr(tc, "function", None)
                if fn and getattr(fn, "arguments", None):
                    fn.arguments = _THINK_RE.sub("", fn.arguments)
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
