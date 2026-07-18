from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the official Apache-2.0 Wan 2.2 runtime and checkpoint.")
    parser.add_argument("--repo-dir", type=Path, default=Path("/opt/Wan2.2"))
    parser.add_argument("--model-dir", type=Path, default=Path("/models/Wan2.2-TI2V-5B"))
    parser.add_argument("--skip-dependencies", action="store_true")
    args = parser.parse_args()

    if not args.repo_dir.exists():
        args.repo_dir.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "https://github.com/Wan-Video/Wan2.2.git", str(args.repo_dir)])
    if not (args.repo_dir / "generate.py").is_file():
        raise SystemExit(f"Invalid Wan repository: {args.repo_dir}")
    if not args.skip_dependencies:
        run([sys.executable, "-m", "pip", "install", "-r", str(args.repo_dir / "requirements.txt")])

    from huggingface_hub import snapshot_download

    args.model_dir.mkdir(parents=True, exist_ok=True)
    print("Downloading Wan-AI/Wan2.2-TI2V-5B. This is approximately 34 GB.")
    snapshot_download(
        repo_id="Wan-AI/Wan2.2-TI2V-5B",
        local_dir=args.model_dir,
    )
    print("Wan 2.2 is ready.")
    print(f"OPENVIDEO_WAN_REPO={args.repo_dir}")
    print(f"OPENVIDEO_WAN_CHECKPOINT={args.model_dir}")


if __name__ == "__main__":
    main()

