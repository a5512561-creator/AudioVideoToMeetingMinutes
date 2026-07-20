"""Build minutes_audio.zip: a self-contained email_with_audio.html that
references 10-second clips by RELATIVE path, plus the clip files. Relative
refs work once the zip is unzipped locally (unlike the SharePoint-viewer case
that needs data: URLs)."""
import json
import zipfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from script.audio_assets import output_audio, clip_start, cut_clips

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _clip_key_for(timestamps, pre, cut_map):
    if not timestamps:
        return None
    s = clip_start(timestamps[0], pre)
    # `s not in cut_map` also covers a clip ffmpeg failed to cut (cut_clips is
    # best-effort and skips failed seeks) — such items just get no ▶ button.
    if s is None or s not in cut_map:
        return None
    return str(s)


def build_audio_zip(synth, out_dir, *, pre_seconds: int, duration: int):
    """Cut clips, render the relative-ref HTML, and zip both. Returns the zip
    Path, or None when no sibling audio is available in out_dir."""
    out_dir = Path(out_dir)
    audio = output_audio(out_dir)
    if audio is None:
        return None

    starts = []
    for t in synth.topics:
        if t.source_timestamps:
            s = clip_start(t.source_timestamps[0], pre_seconds)
            if s is not None:
                starts.append(s)
    for a in synth.action_items:
        if a.source_timestamps:
            s = clip_start(a.source_timestamps[0], pre_seconds)
            if s is not None:
                starts.append(s)

    cut_map = cut_clips(audio, starts, duration, out_dir)  # {start: filename}
    clips_js = {str(s): name for s, name in cut_map.items()}

    topics = [
        {"title": t.title, "summary": t.summary, "decisions": list(t.decisions),
         "clip": _clip_key_for(t.source_timestamps, pre_seconds, cut_map)}
        for t in synth.topics
    ]
    actions = [
        {"idx": i, "task": a.task, "owner": a.owner, "due": a.due,
         "clip": _clip_key_for(a.source_timestamps, pre_seconds, cut_map)}
        for i, a in enumerate(synth.action_items, start=1)
    ]

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    html = env.get_template("email_with_audio.html.j2").render(
        meeting_name=out_dir.name, topics=topics, actions=actions,
        clips_js=json.dumps(clips_js, ensure_ascii=True),
    )

    zip_path = out_dir / "minutes_audio.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("email_with_audio.html", html)
        for name in cut_map.values():
            z.write(out_dir / name, arcname=name)
    return zip_path
