"""Probe the company vLLM transcription endpoint to discover what it supports.

Read-only diagnostic — touches no project code, writes no files. It answers the
four unknowns blocking integration into script/transcribe.py:

  1. Does it return segment-level timestamps (response_format=verbose_json)?
  2. What is the literal `<asr_text>` prefix format in `text`?
  3. Does it accept the standard `language` / `prompt` params?
  4. Which response_format values work at all?

Usage:
  python scripts/probe_transcription.py src/sample.wav
  python scripts/probe_transcription.py src/sample.wav --model aud2txt

API key is read from env (.env is auto-loaded). Never pass it on the CLI.
Set REALGPT_API_KEY=... (or OPENAI_API_KEY=...) and OPENAI_API_BASE=... in .env.
"""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

# Windows consoles default to cp950/cp1252 and choke on CJK + box chars.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ASR_DELIM = "<asr_text>"


def strip_asr_prefix(text: str) -> str:
    """Server prepends 'language <Lang><asr_text>' before the real transcript."""
    if ASR_DELIM in text:
        return text.split(ASR_DELIM, 1)[1].strip()
    return text.strip()


def _short(obj, limit: int = 600) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + f" …(+{len(s) - limit} chars)"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", help="path to a short test audio file (e.g. src/sample.wav)")
    p.add_argument("--model", default="aud2txt")
    p.add_argument("--api-base", default=None, help="overrides OPENAI_API_BASE from .env")
    p.add_argument("--language", default="zh", help="language hint to probe (default: zh)")
    p.add_argument("--prompt", default="以下是繁體中文會議錄音。", help="prompt hint to probe")
    p.add_argument("--timeout", type=float, default=300.0)
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env")

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        print(f"ERROR: audio file not found: {audio_path}", file=sys.stderr)
        return 2

    api_key = os.getenv("REALGPT_API_KEY") or os.getenv("OPENAI_API_KEY")
    api_base = args.api_base or os.getenv("OPENAI_API_BASE")
    if not api_key or not api_base:
        print("ERROR: set REALGPT_API_KEY (or OPENAI_API_KEY) and OPENAI_API_BASE in .env",
              file=sys.stderr)
        return 2

    size_mb = audio_path.stat().st_size / 1_048_576
    print(f"endpoint : {api_base}")
    print(f"model    : {args.model}")
    print(f"audio    : {audio_path}  ({size_mb:.2f} MB)")
    print("=" * 70)

    client = OpenAI(api_key=api_key, base_url=api_base, timeout=args.timeout)
    caps: dict[str, str] = {}

    # --- Probe 0: raw multipart POST, to see the LITERAL server JSON -------
    # The SDK hides non-standard fields (usage/duration/logprobs); a raw call
    # shows exactly what the server emits, including the <asr_text> prefix.
    print("\n[0] RAW multipart POST  /audio/transcriptions")
    try:
        with open(audio_path, "rb") as f:
            r = httpx.post(
                api_base.rstrip("/") + "/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio_path.name, f, "application/octet-stream")},
                data={"model": args.model},
                timeout=args.timeout,
            )
        print(f"    HTTP {r.status_code}")
        print(f"    body: {_short(r.text)}")
        if r.status_code == 200:
            try:
                body = r.json()
                raw_text = body.get("text", "")
                print(f"    text (raw)    : {_short(raw_text, 300)}")
                print(f"    text (cleaned): {_short(strip_asr_prefix(raw_text), 300)}")
                print(f"    extra keys    : {sorted(set(body) - {'text'})}")
                caps["raw_call"] = "OK"
            except Exception as e:
                caps["raw_call"] = f"200 but non-JSON body ({e})"
        else:
            caps["raw_call"] = f"HTTP {r.status_code}"
    except Exception as e:
        caps["raw_call"] = f"FAIL {type(e).__name__}: {e}"
        print(f"    FAIL: {e}")

    # --- Helper to run an SDK call as an isolated probe -------------------
    def probe(label: str, key: str, **kwargs):
        print(f"\n[{label}]")
        try:
            with open(audio_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    file=f, model=args.model, **kwargs
                )
            dumped = resp.model_dump() if hasattr(resp, "model_dump") else resp
            if isinstance(dumped, dict):
                segs = dumped.get("segments")
                words = dumped.get("words")
                print(f"    type     : dict, keys={sorted(dumped)}")
                if segs:
                    print(f"    segments : {len(segs)}  e.g. {_short(segs[0], 300)}")
                if words:
                    print(f"    words    : {len(words)}  e.g. {_short(words[0], 200)}")
                if "text" in dumped:
                    print(f"    text     : {_short(dumped['text'], 300)}")
                caps[key] = "OK (has segments)" if segs else "OK (no segments)"
            else:
                print(f"    type     : {type(dumped).__name__} (plain string)")
                print(f"    value    : {_short(str(dumped), 400)}")
                caps[key] = "OK (plain text, no timestamps)"
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            print(f"    FAIL: {_short(msg, 400)}")
            caps[key] = "REJECTED " + type(e).__name__

    probe("1] SDK default (response_format unset)", "sdk_default")
    probe("2] SDK response_format=json", "rf_json", response_format="json")
    probe("3] SDK response_format=verbose_json + segment timestamps",
          "rf_verbose_segment",
          response_format="verbose_json", timestamp_granularities=["segment"])
    probe("4] SDK response_format=verbose_json + word timestamps",
          "rf_verbose_word",
          response_format="verbose_json", timestamp_granularities=["word"])
    probe("5] SDK response_format=text", "rf_text", response_format="text")
    probe("6] SDK response_format=srt", "rf_srt", response_format="srt")
    probe(f"7] SDK language={args.language!r}", "param_language",
          language=args.language)
    probe("8] SDK prompt=<zh hint>", "param_prompt", prompt=args.prompt)

    # --- Capability summary ----------------------------------------------
    print("\n" + "=" * 70)
    print("CAPABILITY SUMMARY")
    print("=" * 70)
    for k, v in caps.items():
        print(f"  {k:<22} : {v}")
    print("\nKey questions:")
    print(f"  segment timestamps? -> {caps.get('rf_verbose_segment', 'n/a')}")
    print(f"  language= accepted? -> {caps.get('param_language', 'n/a')}")
    print(f"  prompt=   accepted? -> {caps.get('param_prompt', 'n/a')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
