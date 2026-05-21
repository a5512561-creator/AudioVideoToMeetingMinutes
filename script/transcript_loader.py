import re
from pathlib import Path

# Timestamp on its own line: "MM:SS" or "H:MM:SS"/"HH:MM:SS".
_TS_LINE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")

# WebVTT cue time range: "HH:MM:SS.mmm --> HH:MM:SS.mmm".
# We only capture the START's HH:MM:SS — ms precision is dropped because
# downstream chunker / clip_start work in second granularity.
_VTT_TIME = re.compile(
    r"^\s*(\d{2}):(\d{2}):(\d{2})\.\d+\s+-->\s+\d{2}:\d{2}:\d{2}\.\d+"
)
# Voice tag: "<v Speaker Name>...". May or may not have a closing </v>;
# Teams sometimes splits a single cue's text across multiple lines with the
# closing tag only on the last line.
_VTT_VOICE_OPEN = re.compile(r"<v\s+([^>]+)>")
_VTT_VOICE_CLOSE = re.compile(r"</v>")


def _fmt(h: int, m: int, s: int) -> str:
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def _normalize_android(text: str) -> str:
    """Recorder-style transcript (MM:SS or H:MM:SS block headers, no speakers).

    Each timestamp line opens a block; subsequent non-blank lines are the
    utterance text, joined with single spaces. Output: ``[HH:MM:SS] text``.
    """
    out: list[str] = []
    cur_ts = "[00:00:00]"           # leading text before any timestamp
    buf: list[str] = []

    def flush() -> None:
        joined = " ".join(" ".join(buf).split())
        if joined:
            out.append(f"{cur_ts} {joined}")
        buf.clear()

    for line in text.splitlines():
        m = _TS_LINE.match(line)
        if m:
            flush()
            g1, g2, g3 = m.group(1), m.group(2), m.group(3)
            if g3 is not None:                       # H:MM:SS
                h, mm, ss = int(g1), int(g2), int(g3)
            else:                                    # MM:SS
                h, mm, ss = 0, int(g1), int(g2)
            cur_ts = _fmt(h, mm, ss)
            continue
        if line.strip():
            buf.append(line.strip())
    flush()
    return "\n".join(out) + ("\n" if out else "")


def _normalize_vtt(text: str) -> str:
    """WebVTT cue stream (Teams export) → ``[HH:MM:SS] Speaker: text`` lines.

    One output line per cue. Speaker comes from ``<v Speaker>...</v>``;
    when absent (rare but possible if a participant joins without a tagged
    voice), the line uses the no-speaker form. Multi-line cue text is
    joined with single spaces; ms precision in the start time is dropped.

    Cue terminator is the blank line per VTT spec — closing ``</v>`` is
    not required and may appear on a later text line within the same cue.
    """
    out: list[str] = []
    cur_ts: str | None = None
    cur_speaker: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal cur_ts, cur_speaker
        body = " ".join(" ".join(buf).split())
        if cur_ts is not None and body:
            if cur_speaker:
                out.append(f"{cur_ts} {cur_speaker}: {body}")
            else:
                out.append(f"{cur_ts} {body}")
        buf.clear()
        cur_ts = None
        cur_speaker = None

    for line in text.splitlines():
        m = _VTT_TIME.match(line)
        if m:
            flush()                  # emit previous cue (if any)
            cur_ts = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            continue
        if cur_ts is None:
            # Outside any cue (WEBVTT header, cue-id lines, NOTE blocks,
            # blank lines between cues) — ignore.
            continue
        if not line.strip():
            # VTT cue terminator.
            flush()
            continue
        # Inside a cue: harvest the speaker (first <v ...> wins per cue)
        # then strip the voice tags and append the residual text.
        v = _VTT_VOICE_OPEN.search(line)
        if v and cur_speaker is None:
            cur_speaker = v.group(1).strip()
        cleaned = _VTT_VOICE_CLOSE.sub("", _VTT_VOICE_OPEN.sub("", line)).strip()
        if cleaned:
            buf.append(cleaned)
    flush()                          # tail cue if file lacks trailing blank
    return "\n".join(out) + ("\n" if out else "")


def detect_format(text: str) -> str:
    """Return ``'vtt'`` if first non-blank line starts with WEBVTT, else
    ``'android'``. Empty input defaults to ``'android'``."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return "vtt" if stripped.upper().startswith("WEBVTT") else "android"
    return "android"


def normalize(text: str) -> str:
    """Normalise a meeting transcript to ``[HH:MM:SS] [Speaker: ]text`` lines.

    Auto-detects format via :func:`detect_format`:
    - ``WEBVTT`` header → Microsoft Teams VTT export (carries real speaker
      names via ``<v Name>`` tags)
    - anything else → Android Recorder MM:SS-block format (no speakers)

    Downstream chunker / minutes_agent accept either output shape; speaker
    labels when present feed into prompts and review report unchanged.
    """
    if detect_format(text) == "vtt":
        return _normalize_vtt(text)
    return _normalize_android(text)


def load_transcript(src: str, dst: str) -> str:
    """Read ``src``, write the normalised transcript to ``dst``, return the
    detected source format (``'vtt'`` | ``'android'``).

    Pipeline includes the returned format in ``stage.load_transcript`` log
    so a run's log makes the auto-detection decision auditable.
    """
    raw = Path(src).read_text(encoding="utf-8", errors="replace")
    fmt = detect_format(raw)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(normalize(raw), encoding="utf-8")
    return fmt
