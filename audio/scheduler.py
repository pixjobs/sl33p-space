import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta


@dataclass
class ScheduledRoutine:
    profile_name: str
    sound_type: str
    start_time: str  # HH:MM format
    duration_minutes: int = 30
    fade_out_minutes: int = 15
    volume: int = 40
    recurring: bool = False
    routine_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    active: bool = True


class Scheduler:
    def __init__(self, player, library, data_dir: str = "data"):
        self._player = player
        self._library = library
        self._data_dir = data_dir
        self._schedules_file = os.path.join(data_dir, "schedules.json")
        self._routines: dict[str, ScheduledRoutine] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._load()

    def _load(self):
        if os.path.exists(self._schedules_file):
            with open(self._schedules_file) as f:
                data = json.load(f)
            for item in data:
                r = ScheduledRoutine(**item)
                self._routines[r.routine_id] = r

    def _save(self):
        os.makedirs(self._data_dir, exist_ok=True)
        with open(self._schedules_file, "w") as f:
            json.dump([asdict(r) for r in self._routines.values()], f, indent=2)

    def schedule(self, routine: ScheduledRoutine) -> dict:
        self._routines[routine.routine_id] = routine
        self._save()
        return {"scheduled": routine.routine_id, "time": routine.start_time, "sound": routine.sound_type}

    def cancel(self, routine_id: str) -> dict:
        if routine_id in self._routines:
            del self._routines[routine_id]
            self._save()
            return {"cancelled": routine_id}
        return {"error": f"Routine {routine_id} not found"}

    def list_routines(self) -> list[dict]:
        return [asdict(r) for r in self._routines.values() if r.active]

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run_loop(self):
        triggered_today: set[str] = set()
        while not self._stop_event.is_set():
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            today_key = now.strftime("%Y-%m-%d")

            for rid, routine in list(self._routines.items()):
                if not routine.active:
                    continue
                day_rid = f"{today_key}:{rid}"
                if day_rid in triggered_today:
                    continue
                if routine.start_time == current_time:
                    triggered_today.add(day_rid)
                    self._trigger(routine)

            if now.hour == 0 and now.minute == 0:
                triggered_today.clear()

            self._stop_event.wait(30)

    def _trigger(self, routine: ScheduledRoutine):
        filepath = self._library.get_sound(routine.sound_type, duration_minutes=routine.duration_minutes)
        if not filepath:
            return
        self._player.play(filepath, volume=routine.volume)
        if routine.fade_out_minutes > 0:
            fade_delay = max(0, (routine.duration_minutes - routine.fade_out_minutes) * 60)
            threading.Timer(fade_delay, self._start_fade, args=(routine,)).start()
        else:
            threading.Timer(routine.duration_minutes * 60, self._player.stop).start()

        if not routine.recurring:
            routine.active = False
            self._save()

    def _start_fade(self, routine: ScheduledRoutine):
        if self._player.state.is_playing:
            self._player.fade_to(0, routine.fade_out_minutes * 60)
