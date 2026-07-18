from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

from app.config import settings


class PostprocessError(RuntimeError):
    pass


def _ffmpeg() -> str:
    executable = shutil.which(settings.ffmpeg) or (settings.ffmpeg if Path(settings.ffmpeg).is_file() else None)
    if not executable:
        raise PostprocessError("FFmpeg is required for storyboard assembly but was not found.")
    return str(executable)


def _ffprobe() -> str:
    executable = shutil.which(settings.ffprobe) or (settings.ffprobe if Path(settings.ffprobe).is_file() else None)
    if not executable:
        raise PostprocessError("FFprobe is required for caption timing but was not found.")
    return str(executable)


def probe_duration(video: Path) -> float:
    command = [
        _ffprobe(), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PostprocessError(result.stderr[-2000:])
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise PostprocessError("FFprobe returned an invalid duration.") from exc
    if duration <= 0:
        raise PostprocessError("Video duration must be positive.")
    return duration


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def write_storyboard_captions(clips: list[Path], narrations: list[str], output: Path) -> Path | None:
    cues = []
    cursor = 0.0
    cue_number = 1
    for clip, narration in zip(clips, narrations, strict=True):
        duration = probe_duration(clip)
        cleaned = " ".join(narration.split())
        if cleaned:
            wrapped = "\n".join(textwrap.wrap(cleaned, width=38, max_lines=2, placeholder="…"))
            cues.extend([
                str(cue_number),
                f"{_srt_time(cursor + 0.12)} --> {_srt_time(cursor + max(0.3, duration - 0.12))}",
                wrapped,
                "",
            ])
            cue_number += 1
        cursor += duration
    if not cues:
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(cues), encoding="utf-8")
    return output


def extract_last_frame(video: Path, image: Path) -> Path:
    image.parent.mkdir(parents=True, exist_ok=True)
    command = [_ffmpeg(), "-y", "-sseof", "-0.08", "-i", str(video), "-frames:v", "1", str(image)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PostprocessError(result.stderr[-2000:])
    return image


def concat_clips(clips: list[Path], output: Path) -> Path:
    if len(clips) < 2:
        raise PostprocessError("Storyboard assembly requires at least two clips.")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_suffix(".concat.txt")
    lines = []
    for clip in clips:
        resolved = str(clip.resolve()).replace("'", "'\\''").replace("\\", "/")
        lines.append(f"file '{resolved}'")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = [
        _ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c", "copy", "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PostprocessError(result.stderr[-2000:])
    return output


def mux_narration(video: Path, audio: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg(), "-y", "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
        "-b:a", "192k", "-af", "apad", "-shortest", "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PostprocessError(result.stderr[-2000:])
    return output


def mix_soundtrack(video: Path, output: Path, narration: Path | None = None,
                   music: Path | None = None, music_volume: float = 0.12) -> Path:
    if not narration and not music:
        raise PostprocessError("At least one audio input is required.")
    command = [_ffmpeg(), "-y", "-i", str(video)]
    if narration:
        command.extend(["-i", str(narration)])
    if music:
        command.extend(["-stream_loop", "-1", "-i", str(music)])
    if narration and music:
        audio_filter = (
            f"[1:a]volume=1.0[n];[2:a]volume={music_volume:.3f}[m];"
            "[n][m]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95,apad[a]"
        )
    elif narration:
        audio_filter = "[1:a]volume=1.0,alimiter=limit=0.95,apad[a]"
    else:
        audio_filter = f"[1:a]volume={music_volume:.3f},alimiter=limit=0.95,apad[a]"
    command.extend([
        "-filter_complex", audio_filter, "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", str(output),
    ])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PostprocessError(result.stderr[-2000:])
    return output


def master_video(video: Path, output: Path, aspect: str, captions: Path | None = None) -> Path:
    targets = {
        "vertical": (1080, 1920),
        "landscape": (1920, 1080),
        "square": (1080, 1080),
    }
    if aspect not in targets:
        raise PostprocessError(f"Unsupported mastering aspect: {aspect}")
    width, height = targets[aspect]
    filters = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"minterpolate=fps={settings.target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
    )
    if captions:
        escaped = str(captions.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        margin = 180 if aspect == "vertical" else 70
        filters += (
            f",subtitles=filename='{escaped}':force_style='FontName=Arial,FontSize=26,"
            f"Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,"
            f"Outline=3,Shadow=1,Alignment=2,MarginV={margin}'"
        )
    filters += ",format=yuv420p"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg(), "-y", "-i", str(video), "-vf", filters,
        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PostprocessError(result.stderr[-2000:])
    return output
