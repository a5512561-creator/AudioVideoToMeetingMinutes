import json
from script.agents.base import LLMAgent
from script.schemas import MeetingMinutes, ReviewResult


class ReviewerAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="reviewer",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def review(self, minutes: MeetingMinutes) -> ReviewResult:
        # Embed IDs into the JSON the LLM sees
        payload = {
            "conclusions": [
                {"id": f"C{i+1}", **c.model_dump()}
                for i, c in enumerate(minutes.conclusions)
            ],
            "key_points": [
                {"id": f"K{i+1}", **k.model_dump()}
                for i, k in enumerate(minutes.key_points)
            ],
            "actions": [
                {"id": f"A{i+1}", **a.model_dump()}
                for i, a in enumerate(minutes.actions)
            ],
        }
        sys = self.render("reviewer_system.j2")
        user = self.render(
            "reviewer_user.j2",
            minutes_with_ids_json=json.dumps(payload, ensure_ascii=False),
        )
        return self.call(system=sys, user=user, response_model=ReviewResult)
