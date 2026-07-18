from __future__ import annotations

import logging
import signal
import time
from pathlib import Path

from app.backends.wan22 import Wan22Backend
from app.config import settings
from app.database import JobStore
from app.domain import GenerationSpec, StoryboardSpec
from app.narration import synthesize
from app.postprocess import (
    concat_clips,
    extract_last_frame,
    master_video,
    mix_soundtrack,
    write_storyboard_captions,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("openvideo.worker")
stopping = False


def stop(*_args) -> None:
    global stopping
    stopping = True


def render_storyboard(job_id: str, spec: StoryboardSpec, store: JobStore, backend,
                      assembler=concat_clips, frame_extractor=extract_last_frame,
                      narrator=synthesize, sound_mixer=mix_soundtrack,
                      caption_writer=write_storyboard_captions, masterer=master_video) -> Path:
    root = settings.output_dir / job_id
    shots_dir = root / "shots"
    continuity_dir = root / "continuity"
    shots_dir.mkdir(parents=True, exist_ok=True)
    continuity_dir.mkdir(parents=True, exist_ok=True)
    current = store.get(job_id) or {}
    artifacts = current.get("artifacts") or {"shots": []}
    artifacts["kind"] = "storyboard"
    artifacts["title"] = spec.title
    shot_records = artifacts.setdefault("shots", [])
    while len(shot_records) < len(spec.shots):
        shot_records.append({"status": "queued"})

    clips: list[Path] = []
    total = len(spec.shots)
    for index, shot in enumerate(spec.shots):
        clip = shots_dir / f"{index + 1:02d}.mp4"
        last_frame = continuity_dir / f"{index + 1:02d}-last.png"
        source = shot.source_image
        if spec.continuity and index > 0 and not source:
            previous = continuity_dir / f"{index:02d}-last.png"
            if not previous.is_file():
                frame_extractor(clips[-1], previous)
            source = str(previous)

        if clip.is_file() and clip.stat().st_size > 0:
            shot_records[index] = {"status": "completed", "clip": str(clip), "resumed": True}
        else:
            shot_records[index] = {"status": "running", "clip": str(clip)}
            store.update(job_id, artifacts=artifacts)
            generation = spec.generation_for(index, source)

            def shot_progress(value: int, shot_index=index) -> None:
                current_job = store.get(job_id)
                if current_job and current_job["status"] == "cancelled":
                    raise RuntimeError("Job cancelled")
                overall = 2 + int(((shot_index + value / 100) / total) * 90)
                store.update(job_id, progress=min(overall, 92))

            backend.generate(generation, clip, shot_progress)
            shot_records[index] = {"status": "completed", "clip": str(clip), "resumed": False}
        clips.append(clip)
        if spec.continuity and index < total - 1 and not last_frame.is_file():
            frame_extractor(clip, last_frame)
        store.update(job_id, artifacts=artifacts)

    output = settings.output_dir / f"{job_id}.mp4"
    store.update(job_id, progress=94, artifacts=artifacts)
    assembler(clips, output)
    artifacts["assembled"] = str(output)
    narration_text = " ".join(shot.narration for shot in spec.shots if shot.narration).strip()
    narration_audio = None
    if narration_text and settings.kokoro_url:
        narration_audio = root / "narration.wav"
        narrator(narration_text, narration_audio)
        artifacts["narration"] = {"status": "completed", "audio": str(narration_audio)}
    elif narration_text:
        artifacts["narration"] = {"status": "skipped", "reason": "OPENVIDEO_KOKORO_URL is not configured"}
    music = Path(spec.music_path) if spec.music_path else None
    if narration_audio or music:
        mixed = root / "mixed-audio.mp4"
        sound_mixer(output, mixed, narration=narration_audio, music=music, music_volume=spec.music_volume)
        mixed.replace(output)
        artifacts["audio_mix"] = {
            "status": "completed",
            "narration": bool(narration_audio),
            "music": bool(music),
            "music_volume": spec.music_volume,
        }
    captions = None
    if spec.captions:
        captions = caption_writer(clips, [shot.narration for shot in spec.shots], root / "captions.srt")
        artifacts["captions"] = {"status": "completed" if captions else "skipped", "path": str(captions) if captions else None}
    if settings.mastering:
        master = root / "master.mp4"
        masterer(output, master, spec.aspect, captions=captions)
        master.replace(output)
        artifacts["mastering"] = {"status": "completed", "fps": settings.target_fps, "resolution": "1080p"}
    store.update(job_id, artifacts=artifacts)
    return output


def main() -> None:
    settings.ensure_directories()
    store = JobStore(settings.database)
    recovered = store.recover_interrupted()
    if settings.backend != "wan22":
        raise SystemExit("Only OPENVIDEO_BACKEND=wan22 is a production renderer. Set it explicitly.")
    backend = Wan22Backend()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    log.info("Worker online with backend=%s model=%s", settings.backend, settings.wan_model)
    if recovered:
        log.info("Requeued %s interrupted job(s) for artifact-aware resume", recovered)

    while not stopping:
        job = store.claim_next()
        if not job:
            time.sleep(settings.worker_poll_seconds)
            continue
        job_id = job["id"]
        try:
            if job["spec"].get("kind") == "storyboard":
                storyboard = StoryboardSpec.from_payload(job["spec"])
                output = render_storyboard(job_id, storyboard, store, backend)
            else:
                spec = GenerationSpec.from_payload(job["spec"])
                output = settings.output_dir / f"{job_id}.mp4"

                def progress(value: int) -> None:
                    current = store.get(job_id)
                    if current and current["status"] == "cancelled":
                        raise RuntimeError("Job cancelled")
                    store.update(job_id, progress=value)

                backend.generate(spec, output, progress)
                if settings.mastering:
                    master = settings.output_dir / f"{job_id}-master.mp4"
                    master_video(output, master, spec.aspect)
                    master.replace(output)
            store.update(job_id, status="completed", progress=100, output_path=str(output))
            log.info("Completed job=%s", job_id)
        except Exception as exc:
            current = store.get(job_id)
            status = "cancelled" if current and current["status"] == "cancelled" else "failed"
            store.update(job_id, status=status, error=str(exc)[:2000])
            log.exception("Failed job=%s", job_id)


if __name__ == "__main__":
    main()
