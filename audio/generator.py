import os
import wave
import math
import struct
import random
from dataclasses import dataclass


@dataclass
class AudioSettings:
    sample_rate: int = 44100
    bit_depth: int = 16
    channels: int = 2
    volume: float = 0.5


PENTATONIC_MINOR = [1.0, 1.2, 1.333, 1.5, 1.8, 2.0]
PENTATONIC_MAJOR = [1.0, 1.125, 1.25, 1.5, 1.667, 2.0]
SLEEP_PROGRESSION = [0, 5, 3, 4]
DREAMY_PROGRESSION = [0, 3, 5, 3]

SOUND_TYPES = {
    "brown_noise": "Deep, rumbling noise ideal for masking background sounds",
    "pink_noise": "Balanced noise, softer than white noise",
    "white_noise": "Full-spectrum noise for sound masking",
    "rain": "Rain-like ambient sound with natural modulation",
    "ocean_waves": "Rhythmic ocean wave simulation",
    "binaural_beats": "Stereo beats for deep relaxation (use headphones)",
    "ambient_atmosphere": "Wide stereo pad with gentle movement",
    "lullaby_drone": "Soft harmonic drone with gentle chord changes",
}


class SleepSoundGenerator:
    def __init__(self, output_dir: str = "data/sounds"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.settings = AudioSettings()

    def _init_wav(self, filepath: str, num_samples: int) -> wave.Wave_write:
        wav = wave.open(filepath, "w")
        wav.setnchannels(self.settings.channels)
        wav.setsampwidth(self.settings.bit_depth // 8)
        wav.setframerate(self.settings.sample_rate)
        wav.setnframes(num_samples)
        wav.setcomptype("NONE", "Not Compressed")
        return wav

    def _clamp(self, value: int) -> int:
        return max(-32768, min(32767, value))

    def _fade_envelope(self, i: int, total: int, fade_samples: int) -> float:
        if i < fade_samples:
            return i / fade_samples
        if i > total - fade_samples:
            return (total - i) / fade_samples
        return 1.0

    def generate(self, sound_type: str, duration_minutes: int = 30,
                 volume: float = None, filename: str = None) -> str:
        dispatch = {
            "brown_noise": self._brown_noise,
            "pink_noise": self._pink_noise,
            "white_noise": self._white_noise,
            "rain": self._rain,
            "ocean_waves": self._ocean_waves,
            "binaural_beats": self._binaural_beats,
            "ambient_atmosphere": self._ambient_atmosphere,
            "lullaby_drone": self._lullaby_drone,
        }
        if sound_type not in dispatch:
            raise ValueError(f"Unknown sound type: {sound_type}. Available: {list(dispatch.keys())}")

        vol = volume if volume is not None else self.settings.volume
        fname = filename or f"{sound_type}_{duration_minutes}min"
        filepath = os.path.join(self.output_dir, f"{fname}.wav")

        if os.path.exists(filepath):
            return filepath

        dispatch[sound_type](filepath, duration_minutes * 60, vol)
        return filepath

    def _brown_noise(self, filepath: str, duration_s: float, volume: float):
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        last = 0.0
        for i in range(n):
            white = random.uniform(-1, 1)
            last = (last + 0.02 * white) / 1.02
            env = self._fade_envelope(i, n, fade)
            s = self._clamp(int(last * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", s, s))
        wav.close()

    def _pink_noise(self, filepath: str, duration_s: float, volume: float):
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
        for i in range(n):
            white = random.uniform(-1, 1)
            b0 = 0.99886 * b0 + white * 0.0555179
            b1 = 0.99332 * b1 + white * 0.0750759
            b2 = 0.96900 * b2 + white * 0.1538520
            b3 = 0.86650 * b3 + white * 0.3104856
            b4 = 0.55000 * b4 + white * 0.5329522
            b5 = -0.7616 * b5 - white * 0.0168980
            pink = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11
            env = self._fade_envelope(i, n, fade)
            s = self._clamp(int(pink * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", s, s))
        wav.close()

    def _white_noise(self, filepath: str, duration_s: float, volume: float):
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        for i in range(n):
            env = self._fade_envelope(i, n, fade)
            s = self._clamp(int(random.uniform(-1, 1) * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", s, s))
        wav.close()

    def _rain(self, filepath: str, duration_s: float, volume: float):
        """Pink noise with slow amplitude modulation to simulate rain intensity changes."""
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
        for i in range(n):
            t = i / self.settings.sample_rate
            white = random.uniform(-1, 1)
            b0 = 0.99886 * b0 + white * 0.0555179
            b1 = 0.99332 * b1 + white * 0.0750759
            b2 = 0.96900 * b2 + white * 0.1538520
            b3 = 0.86650 * b3 + white * 0.3104856
            b4 = 0.55000 * b4 + white * 0.5329522
            b5 = -0.7616 * b5 - white * 0.0168980
            pink = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11
            mod = 0.6 + 0.4 * math.sin(2 * math.pi * 0.03 * t + math.sin(2 * math.pi * 0.007 * t))
            env = self._fade_envelope(i, n, fade)
            s = self._clamp(int(pink * mod * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", s, s))
        wav.close()

    def _ocean_waves(self, filepath: str, duration_s: float, volume: float):
        """Brown noise with slow cyclic amplitude for wave-like rhythm."""
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        last = 0.0
        for i in range(n):
            t = i / self.settings.sample_rate
            white = random.uniform(-1, 1)
            last = (last + 0.02 * white) / 1.02
            wave_cycle = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 8.0))
            env = self._fade_envelope(i, n, fade)
            s = self._clamp(int(last * wave_cycle * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", s, s))
        wav.close()

    def _binaural_beats(self, filepath: str, duration_s: float, volume: float):
        """Stereo binaural beats: 100Hz left, 104Hz right (4Hz delta for relaxation)."""
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        base_freq = 100
        beat_freq = 4
        for i in range(n):
            t = i / self.settings.sample_rate
            left = math.sin(2 * math.pi * base_freq * t)
            right = math.sin(2 * math.pi * (base_freq + beat_freq) * t)
            env = self._fade_envelope(i, n, fade)
            l_s = self._clamp(int(left * 32767 * volume * env))
            r_s = self._clamp(int(right * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", l_s, r_s))
        wav.close()

    def _ambient_atmosphere(self, filepath: str, duration_s: float, volume: float):
        """Wide stereo pad with detuned sine waves and slow movement."""
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        for i in range(n):
            t = i / self.settings.sample_rate
            left = math.sin(2 * math.pi * 44.0 * t) * 0.5 + math.sin(2 * math.pi * 66.0 * t) * 0.3
            right = math.sin(2 * math.pi * 44.5 * t) * 0.5 + math.sin(2 * math.pi * 66.2 * t) * 0.3
            mod = 0.7 + 0.3 * math.sin(2 * math.pi * 0.05 * t)
            env = self._fade_envelope(i, n, fade)
            l_s = self._clamp(int(left * mod * 32767 * volume * env))
            r_s = self._clamp(int(right * mod * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", l_s, r_s))
        wav.close()

    def _lullaby_drone(self, filepath: str, duration_s: float, volume: float):
        """Gentle chord drone with slow harmonic progression."""
        n = int(self.settings.sample_rate * duration_s)
        fade = self.settings.sample_rate * 5
        wav = self._init_wav(filepath, n)
        scale = PENTATONIC_MINOR
        progression = SLEEP_PROGRESSION
        base = 65.41  # C2
        chord_dur = duration_s / len(progression)
        for i in range(n):
            t = i / self.settings.sample_rate
            chord_idx = int(t / chord_dur) % len(progression)
            degree = progression[chord_idx]
            chord_freq = base * scale[degree % len(scale)]
            melody_idx = int(t * 1.5) % len(scale)
            melody_freq = base * 2 * scale[melody_idx]
            sample = (
                math.sin(2 * math.pi * chord_freq * t) * 0.5
                + math.sin(2 * math.pi * melody_freq * t) * 0.25
                + math.sin(2 * math.pi * chord_freq * 2 * t) * 0.15
            )
            stereo = math.sin(t * 0.1)
            env = self._fade_envelope(i, n, fade)
            l_s = self._clamp(int(sample * (0.5 + 0.5 * stereo) * 32767 * volume * env))
            r_s = self._clamp(int(sample * (0.5 - 0.5 * stereo) * 32767 * volume * env))
            wav.writeframes(struct.pack("<hh", l_s, r_s))
        wav.close()
