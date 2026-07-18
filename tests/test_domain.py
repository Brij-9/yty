import unittest

from app.domain import GenerationSpec, StoryboardSpec, ValidationError


class GenerationSpecTests(unittest.TestCase):
    def test_valid_vertical_cinematic_spec(self):
        spec = GenerationSpec.from_payload({
            "prompt": "A spacecraft descends through the clouds of Venus.",
            "aspect": "vertical",
            "preset": "cinematic",
            "seed": 42,
        })
        self.assertEqual((spec.width, spec.height), (704, 1280))
        self.assertEqual(spec.render["frames"], 121)

    def test_rejects_short_prompt(self):
        with self.assertRaises(ValidationError):
            GenerationSpec.from_payload({"prompt": "space"})

    def test_rejects_unknown_preset(self):
        with self.assertRaises(ValidationError):
            GenerationSpec.from_payload({"prompt": "A long and valid cinematic prompt", "preset": "magic"})

    def test_rejects_invalid_seed(self):
        with self.assertRaises(ValidationError):
            GenerationSpec.from_payload({"prompt": "A long and valid cinematic prompt", "seed": "wrong"})

    def test_storyboard_builds_continuous_generation_specs(self):
        storyboard = StoryboardSpec.from_payload({
            "title": "Venus descent",
            "seed": 100,
            "shots": [
                {"prompt": "A probe approaches Venus in a wide orbital tracking shot"},
                {"prompt": "The same probe descends through turbulent amber clouds"},
            ],
        })
        second = storyboard.generation_for(1, "continuity.png")
        self.assertEqual(second.seed, 101)
        self.assertEqual(second.source_image, "continuity.png")

    def test_storyboard_requires_multiple_shots(self):
        with self.assertRaises(ValidationError):
            StoryboardSpec.from_payload({
                "shots": [{"prompt": "Only one valid but insufficient cinematic shot"}],
            })

    def test_storyboard_rejects_unsafe_music_level(self):
        with self.assertRaises(ValidationError):
            StoryboardSpec.from_payload({
                "music_volume": 0.9,
                "shots": [
                    {"prompt": "The first sufficiently descriptive cinematic shot"},
                    {"prompt": "The second sufficiently descriptive cinematic shot"},
                ],
            })


if __name__ == "__main__":
    unittest.main()
