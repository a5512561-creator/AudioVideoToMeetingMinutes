import re
from dataclasses import dataclass

try:
    import tiktoken
    _enc = tiktoken.get_encoding("o200k_base")

    def _tiktoken_count(s: str) -> int | None:
        try:
            return len(_enc.encode(s))
        except Exception:
            return None
except Exception:    # tiktoken not importable
    def _tiktoken_count(s: str) -> int | None:    # type: ignore[no-redef]
        return None


_TS_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]")


@dataclass(frozen=True)
class Chunk:
    text: str
    first_timestamp: str
    last_timestamp: str
    token_estimate: int


def estimate_tokens(s: str) -> int:
    n = _tiktoken_count(s)
    if n is not None:
        return n
    return int(len(s) * 1.5)


def _first_ts(line: str) -> str | None:
    m = _TS_RE.match(line)
    return m.group(1) if m else None


def chunk_transcript(text: str, *, max_tokens: int, overlap_ratio: float) -> list[Chunk]:
    """Split a [HH:MM:SS]-prefixed transcript into recursive sentence-bounded chunks."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    chunks: list[Chunk] = []
    i = 0
    while i < len(lines):
        buf: list[str] = []
        buf_tokens = 0
        j = i
        while j < len(lines):
            tentative = buf_tokens + estimate_tokens(lines[j]) + 1
            if buf and tentative > max_tokens:
                break
            buf.append(lines[j])
            buf_tokens = tentative
            j += 1

        # Prepend overlap lines from the previous chunk's tail
        if chunks:
            prev_lines = chunks[-1].text.splitlines()
            overlap_count = max(1, int(len(prev_lines) * overlap_ratio))
            overlap_lines = prev_lines[-overlap_count:]
        else:
            overlap_lines = []

        full_lines = overlap_lines + buf
        full_text = "\n".join(full_lines)

        first = _first_ts(full_lines[0]) or ""
        last = _first_ts(full_lines[-1]) or first
        chunks.append(
            Chunk(
                text=full_text,
                first_timestamp=first,
                last_timestamp=last,
                token_estimate=estimate_tokens("\n".join(buf)),
            )
        )

        if j >= len(lines):
            break
        i = j  # always advance past current non-overlapping content

    return chunks
