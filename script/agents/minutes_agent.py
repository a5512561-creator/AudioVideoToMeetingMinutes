import json
from concurrent.futures import ThreadPoolExecutor
from script.agents.base import LLMAgent
from script.chunker import Chunk
from script.schemas import ChunkExtract, MeetingMinutes


class MinutesAgent(LLMAgent):
    def __init__(self, *, prompts_dir: str, client, model: str, instructor_mode: str):
        super().__init__(
            name="minutes",
            prompts_dir=prompts_dir,
            client=client,
            model=model,
            instructor_mode=instructor_mode,
        )

    def map_chunks(self, chunks: list[Chunk], *, parallel: int) -> list[ChunkExtract]:
        sys = self.render("minutes_system.j2")

        def _one(c: Chunk) -> ChunkExtract:
            user = self.render(
                "minutes_map.j2",
                chunk_text=c.text,
                first_timestamp=c.first_timestamp,
                last_timestamp=c.last_timestamp,
            )
            return self.call(system=sys, user=user, response_model=ChunkExtract)

        if parallel <= 1:
            return [_one(c) for c in chunks]
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            return list(ex.map(_one, chunks))

    def reduce(
        self,
        extracts: list[ChunkExtract],
        *,
        max_input_chars: int,
    ) -> MeetingMinutes:
        sys = self.render("minutes_system.j2")
        return self._reduce_recursive(extracts, sys=sys, max_input_chars=max_input_chars)

    def _reduce_recursive(
        self,
        extracts: list[ChunkExtract],
        *,
        sys: str,
        max_input_chars: int,
    ) -> MeetingMinutes:
        payload = json.dumps([e.model_dump() for e in extracts], ensure_ascii=False)
        if len(payload) <= max_input_chars or len(extracts) <= 2:
            user = self.render("minutes_reduce.j2", chunk_extracts_json=payload)
            return self.call(system=sys, user=user, response_model=MeetingMinutes)
        # Tree reduce: pairwise merge then recurse
        partials: list[ChunkExtract] = []
        for i in range(0, len(extracts), 2):
            pair = extracts[i:i + 2]
            sub_payload = json.dumps([e.model_dump() for e in pair], ensure_ascii=False)
            user = self.render("minutes_reduce.j2", chunk_extracts_json=sub_payload)
            mm = self.call(system=sys, user=user, response_model=MeetingMinutes)
            partials.append(
                ChunkExtract(topics=[], conclusions=mm.conclusions, actions=mm.actions, key_points=mm.key_points)
            )
        return self._reduce_recursive(partials, sys=sys, max_input_chars=max_input_chars)

    @staticmethod
    def assign_ids(minutes: MeetingMinutes) -> dict:
        out: dict = {}
        for i, c in enumerate(minutes.conclusions, start=1):
            out[f"C{i}"] = c
        for i, k in enumerate(minutes.key_points, start=1):
            out[f"K{i}"] = k
        for i, a in enumerate(minutes.actions, start=1):
            out[f"A{i}"] = a
        return out
