from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from app.config import settings


class NarrationError(RuntimeError):
    pass


def synthesize(text: str, output: Path, opener=urllib.request.urlopen) -> Path:
    if not settings.kokoro_url:
        raise NarrationError("OPENVIDEO_KOKORO_URL is not configured.")
    cleaned = " ".join(text.split())
    if not cleaned:
        raise NarrationError("Narration text is empty.")
    payload = json.dumps({
        "model": "kokoro",
        "input": cleaned,
        "voice": settings.kokoro_voice,
        "response_format": "wav",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{settings.kokoro_url}/v1/audio/speech",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=300) as response:
            audio = response.read(50 * 1024 * 1024 + 1)
    except Exception as exc:
        raise NarrationError(f"Local Kokoro request failed: {exc}") from exc
    if len(audio) > 50 * 1024 * 1024:
        raise NarrationError("Local Kokoro response exceeded 50 MB.")
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise NarrationError("Local Kokoro did not return a valid WAV file.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)
    return output
