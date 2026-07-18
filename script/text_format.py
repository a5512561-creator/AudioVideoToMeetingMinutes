"""Shared text helpers for the HTML / email renderers.

Kept separate from the writers so the same logic (and its tests) is reused by
both the web `minutes.html` and the Outlook `minutes_email.html` templates,
registered there as a Jinja filter.
"""
import re

# Split *after* a sentence terminator (CJK 。！？ or ASCII . ! ?) so the
# terminator stays attached to its sentence. A trailing bracket/quote that
# hugs the terminator is kept with the sentence too.
_SENT_END = re.compile(r"(?<=[。！？!?])(?=.)")


def to_sentences(text: str) -> list[str]:
    """Break a summary blob into display sentences for a numbered list.

    Splits on explicit newlines first (authors sometimes pre-bullet), then on
    sentence terminators. Blank fragments are dropped. Text with no terminator
    comes back as a single one-item list, so a short summary still renders as
    one clean line rather than an empty list.
    """
    if not text:
        return []
    out: list[str] = []
    for line in text.replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        for sentence in _SENT_END.split(line):
            sentence = sentence.strip()
            if sentence:
                out.append(sentence)
    return out
