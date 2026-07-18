from __future__ import annotations

from dataclasses import dataclass


ASPECTS = {
    "vertical": (704, 1280),
    "landscape": (1280, 704),
    "square": (960, 960),
}

PRESETS = {
    "preview": {"frames": 49, "steps": 20, "fps": 16},
    "balanced": {"frames": 81, "steps": 30, "fps": 16},
    "cinematic": {"frames": 121, "steps": 40, "fps": 24},
}


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class GenerationSpec:
    prompt: str
    negative_prompt: str
    aspect: str
    preset: str
    seed: int
    source_image: str | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> "GenerationSpec":
        prompt = str(payload.get("prompt", "")).strip()
        if not 12 <= len(prompt) <= 1800:
            raise ValidationError("Prompt must contain between 12 and 1800 characters.")
        negative = str(payload.get("negative_prompt", "")).strip()
        if len(negative) > 1200:
            raise ValidationError("Negative prompt must be 1200 characters or fewer.")
        aspect = str(payload.get("aspect", "vertical"))
        if aspect not in ASPECTS:
            raise ValidationError(f"Unsupported aspect: {aspect}")
        preset = str(payload.get("preset", "balanced"))
        if preset not in PRESETS:
            raise ValidationError(f"Unsupported preset: {preset}")
        try:
            seed = int(payload.get("seed", -1))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Seed must be an integer.") from exc
        if seed < -1 or seed > 2**63 - 1:
            raise ValidationError("Seed is out of range.")
        source_image = payload.get("source_image") or None
        return cls(prompt, negative, aspect, preset, seed, source_image)

    @property
    def width(self) -> int:
        return ASPECTS[self.aspect][0]

    @property
    def height(self) -> int:
        return ASPECTS[self.aspect][1]

    @property
    def render(self) -> dict:
        return PRESETS[self.preset]


@dataclass(frozen=True)
class ShotSpec:
    prompt: str
    negative_prompt: str = ""
    source_image: str | None = None
    narration: str = ""

    @classmethod
    def from_payload(cls, payload: dict) -> "ShotSpec":
        prompt = str(payload.get("prompt", "")).strip()
        if not 12 <= len(prompt) <= 1200:
            raise ValidationError("Every shot prompt must contain between 12 and 1200 characters.")
        negative = str(payload.get("negative_prompt", "")).strip()
        narration = str(payload.get("narration", "")).strip()
        if len(negative) > 800:
            raise ValidationError("A shot negative prompt must be 800 characters or fewer.")
        if len(narration) > 600:
            raise ValidationError("Shot narration must be 600 characters or fewer.")
        return cls(prompt, negative, payload.get("source_image") or None, narration)


@dataclass(frozen=True)
class StoryboardSpec:
    title: str
    aspect: str
    preset: str
    seed: int
    continuity: bool
    shots: tuple[ShotSpec, ...]
    music_path: str | None = None
    music_volume: float = 0.12
    captions: bool = True
    kind: str = "storyboard"

    @classmethod
    def from_payload(cls, payload: dict) -> "StoryboardSpec":
        title = str(payload.get("title", "Untitled storyboard")).strip()
        if not 1 <= len(title) <= 120:
            raise ValidationError("Storyboard title must contain between 1 and 120 characters.")
        aspect = str(payload.get("aspect", "vertical"))
        preset = str(payload.get("preset", "balanced"))
        if aspect not in ASPECTS:
            raise ValidationError(f"Unsupported aspect: {aspect}")
        if preset not in PRESETS:
            raise ValidationError(f"Unsupported preset: {preset}")
        try:
            seed = int(payload.get("seed", -1))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Seed must be an integer.") from exc
        if seed < -1 or seed > 2**63 - 100:
            raise ValidationError("Seed is out of range.")
        raw_shots = payload.get("shots")
        if not isinstance(raw_shots, list) or not 2 <= len(raw_shots) <= 12:
            raise ValidationError("A storyboard must contain between 2 and 12 shots.")
        shots = tuple(ShotSpec.from_payload(item) for item in raw_shots)
        try:
            music_volume = float(payload.get("music_volume", 0.12))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Music volume must be a number.") from exc
        if not 0 <= music_volume <= 0.5:
            raise ValidationError("Music volume must be between 0 and 0.5.")
        return cls(
            title, aspect, preset, seed, bool(payload.get("continuity", True)), shots,
            payload.get("music_path") or None, music_volume, bool(payload.get("captions", True)),
        )

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "aspect": self.aspect,
            "preset": self.preset,
            "seed": self.seed,
            "continuity": self.continuity,
            "shots": [shot.__dict__ for shot in self.shots],
            "music_path": self.music_path,
            "music_volume": self.music_volume,
            "captions": self.captions,
        }

    def generation_for(self, index: int, source_image: str | None = None) -> GenerationSpec:
        shot = self.shots[index]
        seed = self.seed + index if self.seed >= 0 else -1
        return GenerationSpec(
            prompt=shot.prompt,
            negative_prompt=shot.negative_prompt,
            aspect=self.aspect,
            preset=self.preset,
            seed=seed,
            source_image=shot.source_image or source_image,
        )
