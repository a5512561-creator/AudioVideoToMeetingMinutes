from script.agents.base import LLMAgent
from script.schemas import CorrectionResult


class CorrectorAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="corrector",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def correct(self, *, chunk_text: str, glossary: str) -> CorrectionResult:
        sys = self.render("corrector_system.j2", glossary=glossary)
        user = self.render("corrector_user.j2", chunk_text=chunk_text)
        return self.call(system=sys, user=user, response_model=CorrectionResult)
