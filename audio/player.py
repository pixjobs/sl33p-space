import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass


@dataclass
class PlaybackState:
    filepath: str = ""
    volume: int = 40
    is_playing: bool = False
    started_at: float = 0.0


class AudioPlayer:
    def __init__(self, max_volume: int = 80, default_volume: int = 40):
        self.max_volume = max_volume
        self._state = PlaybackState(volume=default_volume)
        self._process: subprocess.Popen | None = None
        self._fade_thread: threading.Thread | None = None
        self._fade_cancel = threading.Event()
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str | None:
        for cmd in ["aplay", "ffplay", "mpg123", "paplay"]:
            if shutil.which(cmd):
                return cmd
        return None

    @property
    def state(self) -> PlaybackState:
        if self._process and self._process.poll() is not None:
            self._state.is_playing = False
            self._process = None
        return self._state

    def play(self, filepath: str, volume: int | None = None) -> dict:
        if not os.path.exists(filepath):
            return {"error": f"File not found: {filepath}"}

        self.stop()

        if volume is not None:
            self._state.volume = min(volume, self.max_volume)

        self._set_system_volume(self._state.volume)

        if not self._backend:
            self._state.filepath = filepath
            self._state.is_playing = True
            self._state.started_at = time.time()
            return {"status": "simulated", "file": filepath, "note": "No audio backend found"}

        cmd = self._build_play_cmd(filepath)
        self._process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self._state.filepath = filepath
        self._state.is_playing = True
        self._state.started_at = time.time()
        return {"status": "playing", "file": filepath, "backend": self._backend}

    def stop(self) -> dict:
        self._fade_cancel.set()
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._state.is_playing = False
        self._state.filepath = ""
        return {"status": "stopped"}

    def set_volume(self, level: int) -> dict:
        level = max(0, min(level, self.max_volume))
        self._state.volume = level
        self._set_system_volume(level)
        return {"volume": level}

    def fade_to(self, target: int, duration_seconds: int) -> dict:
        target = max(0, min(target, self.max_volume))
        self._fade_cancel.clear()

        def _fade():
            start_vol = self._state.volume
            steps = max(1, abs(start_vol - target))
            step_time = duration_seconds / steps
            direction = 1 if target > start_vol else -1
            for i in range(steps):
                if self._fade_cancel.is_set():
                    return
                new_vol = start_vol + direction * (i + 1)
                self.set_volume(new_vol)
                time.sleep(step_time)
            self.set_volume(target)
            if target == 0:
                self.stop()

        self._fade_thread = threading.Thread(target=_fade, daemon=True)
        self._fade_thread.start()
        return {"status": "fading", "from": self._state.volume, "to": target, "seconds": duration_seconds}

    def _build_play_cmd(self, filepath: str) -> list[str]:
        if self._backend == "aplay":
            return ["aplay", "-q", filepath]
        if self._backend == "ffplay":
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", filepath]
        if self._backend == "mpg123":
            return ["mpg123", "-q", filepath]
        if self._backend == "paplay":
            return ["paplay", filepath]
        return []

    def _set_system_volume(self, level: int):
        if shutil.which("amixer"):
            subprocess.run(
                ["amixer", "sset", "Master", f"{level}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif shutil.which("pactl"):
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
