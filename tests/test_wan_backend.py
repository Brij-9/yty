import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.backends.wan22 import Wan22Backend
from app.config import settings
from app.domain import GenerationSpec


class WanBackendTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.repo = self.root / "Wan2.2"
        self.checkpoint = self.root / "model"
        self.repo.mkdir()
        self.checkpoint.mkdir()
        (self.repo / "generate.py").write_text("# test", encoding="utf-8")
        self.old_values = (settings.wan_engine, settings.wan_repo, settings.wan_checkpoint)
        object.__setattr__(settings, "wan_engine", "official")
        object.__setattr__(settings, "wan_repo", self.repo)
        object.__setattr__(settings, "wan_checkpoint", self.checkpoint)

    def tearDown(self):
        object.__setattr__(settings, "wan_engine", self.old_values[0])
        object.__setattr__(settings, "wan_repo", self.old_values[1])
        object.__setattr__(settings, "wan_checkpoint", self.old_values[2])
        shutil.rmtree(self.root, ignore_errors=True)

    def test_official_engine_passes_reference_image(self):
        source = self.root / "source.png"
        source.write_bytes(b"image")
        output = self.root / "output.mp4"
        spec = GenerationSpec(
            prompt="A coherent cinematic spacecraft moves through dense clouds",
            negative_prompt="",
            aspect="vertical",
            preset="preview",
            seed=44,
            source_image=str(source),
        )
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            Path(command[command.index("--save_file") + 1]).write_bytes(b"video")
            return type("Result", (), {"returncode": 0, "stderr": ""})()

        progress = []
        with patch("app.backends.wan22.subprocess.run", side_effect=fake_run):
            Wan22Backend().generate(spec, output, progress.append)
        self.assertIn("--image", captured["command"])
        self.assertEqual(captured["command"][captured["command"].index("--size") + 1], "704*1280")
        self.assertEqual(progress, [5, 96])
        self.assertTrue(output.is_file())

    def test_diffusers_engine_rejects_image_checkpoint_mismatch_before_loading(self):
        object.__setattr__(settings, "wan_engine", "diffusers")
        spec = GenerationSpec(
            prompt="A coherent cinematic spacecraft moves through dense clouds",
            negative_prompt="",
            aspect="vertical",
            preset="preview",
            seed=44,
            source_image="source.png",
        )
        with self.assertRaisesRegex(RuntimeError, "text-to-video only"):
            Wan22Backend().generate(spec, self.root / "output.mp4", lambda _value: None)


if __name__ == "__main__":
    unittest.main()

