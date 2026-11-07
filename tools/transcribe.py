"""Transcribe a recorded in-person conversation, fully offline, with faster-whisper.

    python tools/transcribe.py <audio file> [--title "Acme demo"] [--model small] [--language en]

Creates data/calls/<call_id>/ with:
    audio.<ext>        a copy of the recording
    transcript.json    segments with start/end times, numbered from 0
    transcript.md      the same, readable, one numbered line per segment
and prints the call id plus a short summary for the agent to act on.

Whisper does not tell speakers apart. The scribe agent labels speakers afterwards
(see tools/speakers.py), which is reliable for two- or three-person conversations.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from common import CALLS, fmt_ts, slugify, utf8_stdout, write_json

DEFAULT_MODEL = os.environ.get("FIELDNOTES_WHISPER_MODEL", "small")


def decode_audio(path: Path):
    """Decode any format a phone produces (ogg/opus voice notes, m4a, mp3, wav) to 16 kHz mono
    float32 with ffmpeg. Done here rather than through PyAV, whose API changes break
    faster-whisper's own decoder between releases."""
    import numpy as np

    if shutil.which("ffmpeg") is None:
        raise SystemExit("error: ffmpeg is not on PATH. Install it (winget install ffmpeg / brew install ffmpeg / apt install ffmpeg).")
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"error: ffmpeg could not decode {path}: {proc.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0


def main() -> None:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--title", default="", help="short label, e.g. the account name")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="whisper model: tiny, base, small, medium, large-v3")
    parser.add_argument("--language", default=None, help="force a language code (default: auto-detect)")
    parser.add_argument("--call-id", default=None, help="reuse/overwrite a specific call id")
    args = parser.parse_args()

    if not args.audio.is_file():
        raise SystemExit(f"error: audio file not found: {args.audio}")

    # Imported here so `--help` works before the model is installed.
    from faster_whisper import WhisperModel

    started = datetime.now()
    call_id = args.call_id or f"{started:%Y%m%d-%H%M}-{slugify(args.title or args.audio.stem)}"
    folder = CALLS / call_id
    folder.mkdir(parents=True, exist_ok=True)
    audio_copy = folder / f"audio{args.audio.suffix.lower() or '.bin'}"
    if args.audio.resolve() != audio_copy.resolve():
        shutil.copyfile(args.audio, audio_copy)

    print(f"call_id: {call_id}")
    print(f"loading whisper model '{args.model}' (first run downloads it)...", flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    t0 = time.time()
    segments_iter, info = model.transcribe(
        decode_audio(audio_copy),
        language=args.language,
        vad_filter=True,
        beam_size=5,
    )
    print(f"language: {info.language} (p={info.language_probability:.2f}), duration: {fmt_ts(info.duration)}", flush=True)

    segments = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append({"i": len(segments), "start": round(seg.start, 2), "end": round(seg.end, 2), "text": text})
    elapsed = time.time() - t0

    transcript = {
        "call_id": call_id,
        "title": args.title,
        "source_file": args.audio.name,
        "recorded_at": started.isoformat(timespec="seconds"),
        "language": info.language,
        "duration_sec": round(info.duration, 1),
        "model": args.model,
        "segments": segments,
    }
    write_json(folder / "transcript.json", transcript)

    lines = [f"# Transcript: {args.title or call_id}", "", f"Duration {fmt_ts(info.duration)} · language {info.language} · {len(segments)} segments", ""]
    lines += [f"[{s['i']}] ({fmt_ts(s['start'])}) {s['text']}" for s in segments]
    (folder / "transcript.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    words = sum(len(s["text"].split()) for s in segments)
    print(f"segments: {len(segments)}, words: {words}, transcribed in {elapsed:.0f}s")
    print(f"wrote: {folder / 'transcript.md'}")
    print("next: label speakers with tools/speakers.py, then write notes.md")


if __name__ == "__main__":
    main()
