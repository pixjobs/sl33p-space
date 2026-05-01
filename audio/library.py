import os
import json
from audio.generator import SleepSoundGenerator, SOUND_TYPES


DEFAULT_SOUNDS = [
    ("brown_noise", 30),
    ("pink_noise", 30),
    ("rain", 30),
    ("ocean_waves", 30),
    ("lullaby_drone", 30),
    ("binaural_beats", 30),
    ("ambient_atmosphere", 30),
    ("white_noise", 30),
]


class SoundLibrary:
    def __init__(self, sounds_dir: str = "data/sounds"):
        self._dir = sounds_dir
        self._generator = SleepSoundGenerator(output_dir=sounds_dir)
        os.makedirs(sounds_dir, exist_ok=True)

    def list_sounds(self) -> list[dict]:
        sounds = []
        for f in sorted(os.listdir(self._dir)):
            if f.endswith(".wav"):
                name = f.replace(".wav", "")
                size_mb = os.path.getsize(os.path.join(self._dir, f)) / (1024 * 1024)
                sound_type = next((k for k in SOUND_TYPES if name.startswith(k)), "custom")
                sounds.append({
                    "name": name,
                    "filename": f,
                    "type": sound_type,
                    "description": SOUND_TYPES.get(sound_type, "Custom sound"),
                    "size_mb": round(size_mb, 1),
                    "path": os.path.join(self._dir, f),
                })
        return sounds

    def get_sound(self, sound_type: str, duration_minutes: int = 30) -> str | None:
        filename = f"{sound_type}_{duration_minutes}min"
        filepath = os.path.join(self._dir, f"{filename}.wav")
        if os.path.exists(filepath):
            return filepath
        if sound_type in SOUND_TYPES:
            return self._generator.generate(sound_type, duration_minutes, filename=filename)
        return None

    def generate_custom(self, sound_type: str, duration_minutes: int,
                        volume: float = 0.5, name: str = None) -> dict:
        if sound_type not in SOUND_TYPES:
            return {"error": f"Unknown type. Available: {list(SOUND_TYPES.keys())}"}
        filepath = self._generator.generate(
            sound_type, duration_minutes, volume=volume,
            filename=name or f"{sound_type}_{duration_minutes}min_custom"
        )
        return {"path": filepath, "type": sound_type, "duration": duration_minutes}

    def ensure_defaults(self, callback=None):
        for sound_type, duration in DEFAULT_SOUNDS:
            filepath = self.get_sound(sound_type, duration)
            if callback:
                callback(sound_type, filepath)

    def get_types(self) -> dict[str, str]:
        return dict(SOUND_TYPES)
