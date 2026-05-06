import json
from dataclasses import dataclass
from pathlib import Path
import instructor
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel


@dataclass(frozen=True)
class FewShot:
    input: str
    output: str


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
    """Probe the OpenAI-compat server for strict JSON_SCHEMA support.

    Returns "JSON_SCHEMA" if a tiny request succeeds with response_format json_schema,
    else "JSON" (broadly compatible fallback).
    """
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "probe",
                    "strict": True,
                    "schema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
            max_tokens=4,
        )
        return "JSON_SCHEMA"
    except Exception:
        return "JSON"
