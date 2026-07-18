from __future__ import annotations

import json
import platform
import shutil
import subprocess


def gpu_info():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    result = subprocess.run(
        [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        return None
    name, memory, driver = [part.strip() for part in result.stdout.splitlines()[0].split(",")]
    return {"name": name, "vram_mb": int(memory), "driver": driver}


gpu = gpu_info()
report = {
    "os": platform.platform(),
    "python": platform.python_version(),
    "system_ram_gb": round((getattr(__import__('os'), 'sysconf', lambda _x: 0)('SC_PHYS_PAGES') * getattr(__import__('os'), 'sysconf', lambda _x: 0)('SC_PAGE_SIZE')) / 1024**3, 1) if platform.system() != "Windows" else "inspect with system settings",
    "nvidia_gpu": gpu,
    "wan22_quality_worker_ready": bool(gpu and gpu["vram_mb"] >= 24000),
    "ffmpeg": shutil.which("ffmpeg"),
}
print(json.dumps(report, indent=2))

