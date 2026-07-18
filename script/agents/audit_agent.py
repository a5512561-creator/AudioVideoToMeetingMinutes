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
        return (Path(self.prompts_dir) / "audit_checklist.md").read_text(encoding="utf-8")

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
