from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.domain import GenerationSpec


QUALITY_SUFFIX = (
    "Cinematic physically coherent motion, temporal consistency, realistic materials, "
    "natural parallax, controlled camera movement, filmic lighting, detailed environment, "
    "stable geometry, no text, no watermark."
)

DEFAULT_NEGATIVE = (
    "static frame, slideshow, flicker, jitter, morphing, warped geometry, duplicate objects, "
    "blurry details, oversaturated, low contrast, subtitles, logo, watermark"
)


class Wan22Backend:
    """Wan 2.2 TI2V backend using official GitHub inference or text-only Diffusers."""

    def __init__(self) -> None:
        self.pipe = None

    def generate(self, spec: GenerationSpec, output: Path, progress) -> Path:
        if settings.wan_engine == "official":
            return self._generate_official(spec, output, progress)
        if settings.wan_engine == "diffusers":
            return self._generate_diffusers(spec, output, progress)
        raise RuntimeError("OPENVIDEO_WAN_ENGINE must be 'official' or 'diffusers'.")

    def _generate_official(self, spec: GenerationSpec, output: Path, progress) -> Path:
        script = settings.wan_repo / "generate.py"
        if not script.is_file():
            raise RuntimeError(
                f"Official Wan repository not found at {settings.wan_repo}. "
                "Run python scripts/bootstrap_wan.py on the GPU worker."
            )
        if not settings.wan_checkpoint.is_dir():
            raise RuntimeError(
                f"Wan checkpoint not found at {settings.wan_checkpoint}. "
                "Run python scripts/bootstrap_wan.py on the GPU worker."
            )
        seed = spec.seed if spec.seed >= 0 else random.SystemRandom().randint(0, 2**31 - 1)
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable, str(script),
            "--task", "ti2v-5B",
            "--size", f"{spec.width}*{spec.height}",
            "--ckpt_dir", str(settings.wan_checkpoint),
            "--offload_model", "True",
            "--convert_model_dtype",
            "--t5_cpu",
            "--prompt", f"{spec.prompt.strip()} {QUALITY_SUFFIX}",
            "--base_seed", str(seed),
            "--sample_steps", str(spec.render["steps"]),
            "--save_file", str(output),
        ]
        if spec.source_image:
            command.extend(["--image", spec.source_image])
        progress(5)
        result = subprocess.run(
            command,
            cwd=settings.wan_repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Official Wan inference failed: {result.stderr[-4000:]}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Official Wan inference completed without a video artifact.")
        progress(96)
        return output

    def _load_diffusers(self):
        if self.pipe is not None:
            return self.pipe
        import torch
        from diffusers import DiffusionPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("Wan 2.2 quality rendering requires an NVIDIA CUDA GPU.")
        dtype = getattr(torch, settings.dtype)
        self.pipe = DiffusionPipeline.from_pretrained(
            settings.wan_model,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        )
        if settings.cpu_offload:
            self.pipe.enable_model_cpu_offload()
        else:
            self.pipe.to(settings.device)
        if hasattr(self.pipe, "vae"):
            self.pipe.vae.enable_tiling()
        return self.pipe

    def _generate_diffusers(self, spec: GenerationSpec, output: Path, progress) -> Path:
        if spec.source_image:
            raise RuntimeError(
                "The selected Diffusers checkpoint is text-to-video only. "
                "Set OPENVIDEO_WAN_ENGINE=official for image-guided Wan 2.2 generation."
            )
        import torch
        from diffusers.utils import export_to_video

        pipe = self._load_diffusers()
        seed = spec.seed if spec.seed >= 0 else random.SystemRandom().randint(0, 2**63 - 1)
        generator = torch.Generator(device="cpu").manual_seed(seed)

        def callback(_pipe, step, _timestep, callback_kwargs):
            progress(min(90, 5 + int((step + 1) / spec.render["steps"] * 85)))
            return callback_kwargs

        progress(4)
        result = pipe(
            prompt=f"{spec.prompt.strip()} {QUALITY_SUFFIX}",
            negative_prompt=f"{spec.negative_prompt}, {DEFAULT_NEGATIVE}".strip(", "),
            height=spec.height,
            width=spec.width,
            num_frames=spec.render["frames"],
            num_inference_steps=spec.render["steps"],
            generator=generator,
            callback_on_step_end=callback,
        )
        frames = getattr(result, "frames", None)
        if frames is None:
            raise RuntimeError("The Wan Diffusers pipeline returned no video frames.")
        output.parent.mkdir(parents=True, exist_ok=True)
        export_to_video(frames[0], str(output), fps=spec.render["fps"])
        progress(96)
        return output

