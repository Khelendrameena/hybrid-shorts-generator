"""ModelManager — the VRAM discipline for an RTX 3050 (4 GB).

Rule: at most ONE heavy model resident at a time.
  Whisper-small (~1 GB fp16) → Laya-multilingual (~0.65 GB fp16 / 1.3 GB fp32)
  → Ollama qwen3:4b (~2.5 GB Q4, separate process, unloaded via keep_alive=0)
Loading one evicts the others. Also exposes RAM/VRAM snapshots via psutil /
nvidia-smi when available (never crashes if they are not).
"""
from __future__ import annotations

import gc
import subprocess
import threading


class ModelManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._resident: dict[str, object] = {}
        self.active: str | None = None

    def register(self, name: str, obj) -> None:
        self._resident[name] = obj

    def release(self, name: str) -> None:
        self._resident.pop(name, None)
        if self.active == name:
            self.active = None
        gc.collect()
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def acquire(self, name: str) -> None:
        """Evict every other registered heavy model before `name` loads."""
        with self._lock:
            for other, obj in list(self._resident.items()):
                if other != name and obj is not None:
                    unload = getattr(obj, "unload", None)
                    if callable(unload):
                        try:
                            unload()
                        except Exception:
                            pass
                    self._resident.pop(other, None)
            self.active = name

    def usage(self) -> dict:
        out: dict = {"active_model": self.active, "ram_used_gb": None, "vram_used_mb": None}
        try:
            import psutil  # type: ignore

            out["ram_used_gb"] = round(psutil.virtual_memory().used / 1e9, 2)
            out["ram_total_gb"] = round(psutil.virtual_memory().total / 1e9, 2)
        except Exception:
            pass
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                used, total = r.stdout.strip().splitlines()[0].split(",")
                out["vram_used_mb"] = int(used.strip())
                out["vram_total_mb"] = int(total.strip())
        except Exception:
            pass
        return out


model_manager = ModelManager()
