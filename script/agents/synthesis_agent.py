import json
from script.agents.base import LLMAgent
from script.schemas import MeetingMinutes, MeetingMeta, SynthesizedMinutes


class SynthesisAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="synthesis",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def synthesize(
        self, minutes: MeetingMinutes, meta: MeetingMeta
    ) -> SynthesizedMinutes:
        payload = json.dumps(minutes.model_dump(), ensure_ascii=False)
        sys = self.render("synthesis_system.j2")
        user = self.render("synthesis_user.j2", minutes_json=payload)
        result = self.call(
            system=sys, user=user, response_model=SynthesizedMinutes
        )
        result.meta = meta  # pipeline owns meta; LLM does not produce it
        return result
