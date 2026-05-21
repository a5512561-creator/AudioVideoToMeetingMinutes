import json
from script.agents.base import LLMAgent
from script.schemas import MeetingMinutes, MeetingMeta, ReviewResult, SynthesizedMinutes


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
        self,
        minutes: MeetingMinutes,
        meta: MeetingMeta,
        review: ReviewResult | None = None,
    ) -> SynthesizedMinutes:
        # Embed IDs (C1/K1/A1 …) — mirrors what reviewer_agent shows the LLM
        # so review.notes target_id values point at recognisable items here.
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
        # Only warn/error notes feed back — info-level "OK" entries are noise.
        review_warns = []
        if review is not None:
            review_warns = [
                n.model_dump()
                for n in review.notes
                if n.severity in ("warn", "error")
            ]

        sys = self.render("synthesis_system.j2")
        user = self.render(
            "synthesis_user.j2",
            minutes_json=json.dumps(payload, ensure_ascii=False),
            review_warns=review_warns,
        )
        result = self.call(
            system=sys, user=user, response_model=SynthesizedMinutes
        )
        result.meta = meta  # pipeline owns meta; LLM does not produce it
        return result
