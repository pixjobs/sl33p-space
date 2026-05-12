import os
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
    def __init__(self, max_volume: int = 80, default_volume: int = 40,
                 on_stop_callback=None):
        self.max_volume = max_volume
        self._state = PlaybackState(volume=default_volume)
        self._fade_thread: threading.Thread | None = None
        self._fade_cancel = threading.Event()
        self._on_stop = on_stop_callback

    @property
    def state(self) -> PlaybackState:
        return self._state

    def play(self, filepath: str, volume: int | None = None) -> dict:
        if not os.path.exists(filepath):
            return {"error": f"File not found: {filepath}"}

        self.stop()

        if volume is not None:
            self._state.volume = min(volume, self.max_volume)

        self._state.filepath = filepath
        self._state.is_playing = True
        self._state.started_at = time.time()
        return {"status": "playing", "file": filepath}

    def stop(self, _from_fade: bool = False) -> dict:
        self._fade_cancel.set()
        was_playing = self._state.is_playing
        filepath = self._state.filepath
        self._state.is_playing = False
        self._state.filepath = ""
        if was_playing:
            self._fire_stop_callback(completed=_from_fade, filepath=filepath)
        return {"status": "stopped"}

    def set_volume(self, level: int) -> dict:
        level = max(0, min(level, self.max_volume))
        self._state.volume = level
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
                self.stop(_from_fade=True)

        self._fade_thread = threading.Thread(target=_fade, daemon=True)
        self._fade_thread.start()
        return {"status": "fading", "from": self._state.volume, "to": target, "seconds": duration_seconds}

    def _fire_stop_callback(self, completed: bool = False, filepath: str = None):
        if not self._on_stop:
            return
        fp = filepath or self._state.filepath
        duration = time.time() - self._state.started_at if self._state.started_at else 0
        name = os.path.basename(fp) if fp else ""
        sound = os.path.splitext(name)[0] if name else ""
        try:
            self._on_stop({
                "sound": sound,
                "filepath": fp,
                "duration_seconds": round(duration),
                "completed": completed,
            })
        except Exception:
            pass
