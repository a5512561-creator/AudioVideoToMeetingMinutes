from dataclasses import dataclass
from faster_whisper import WhisperModel


@dataclass(frozen=True)
class Segment:
    start: float    # seconds
    end: float      # seconds
    text: str


def transcribe(
    audio_path: str,
    *,
    model: str,
    device: str,
    compute_type: str,
    language: str,
    initial_prompt: str,
    vad_filter: bool,
) -> list[Segment]:
    m = WhisperModel(model, device=device, compute_type=compute_type)
    raw_segs, _info = m.transcribe(
        audio_path,
        language=language,
        initial_prompt=initial_prompt,
        vad_filter=vad_filter,
    )
    return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in raw_segs]
