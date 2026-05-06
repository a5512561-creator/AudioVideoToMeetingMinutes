from dataclasses import dataclass
from pyannote.audio import Pipeline
from script.transcribe import Segment


@dataclass(frozen=True)
class SpeakerSegment:
    start: float
    end: float
    label: str   # e.g. "SPEAKER_1"


@dataclass(frozen=True)
class TranscribedSegment:
    start: float
    end: float
    text: str
    speaker: str   # "SPEAKER_N" or "UNKNOWN"


def _ensure_torch_load_unsafe() -> None:
    # PyTorch 2.6+ defaults torch.load(weights_only=True). pyannote 3.x
    # checkpoints contain non-tensor objects (TorchVersion, Specifications, ...)
    # that aren't in the default allowlist. Force weights_only=False once;
    # checkpoints come from HF over HTTPS so trust is acceptable.
    import torch
    if getattr(torch.load, "_pyannote_patched", False):
        return
    _orig = torch.load

    def _patched(*a, **kw):
        kw["weights_only"] = False
        return _orig(*a, **kw)

    _patched._pyannote_patched = True  # type: ignore[attr-defined]
    torch.load = _patched


def diarize(audio_path: str, *, model: str, hf_token: str) -> list[SpeakerSegment]:
    _ensure_torch_load_unsafe()
    pipeline = Pipeline.from_pretrained(model, use_auth_token=hf_token)
    annotation = pipeline(audio_path)
    out: list[SpeakerSegment] = []
    for turn, _track, label in annotation.itertracks(yield_label=True):
        out.append(SpeakerSegment(start=turn.start, end=turn.end, label=label))
    return out


def _overlap(a_start, a_end, b_start, b_end) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(
    segments: list[Segment],
    speakers: list[SpeakerSegment],
) -> list[TranscribedSegment]:
    out: list[TranscribedSegment] = []
    for s in segments:
        best: SpeakerSegment | None = None
        best_ov = 0.0
        for sp in speakers:
            ov = _overlap(s.start, s.end, sp.start, sp.end)
            if ov > best_ov:
                best_ov = ov
                best = sp
        label = best.label if best else "UNKNOWN"
        out.append(TranscribedSegment(start=s.start, end=s.end, text=s.text, speaker=label))
    return out
