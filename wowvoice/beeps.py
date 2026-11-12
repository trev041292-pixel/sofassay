"""Short audible cues. Uses winsound, which goes to the default output device."""
from __future__ import annotations

import threading
import winsound

PATTERNS = {
    "start": [(920, 90)],
    "stop": [(620, 90)],
    "sent": [(1200, 55), (1600, 55)],
    "channel": [(1400, 55), (1800, 55)],
    "error": [(300, 240)],
    "busy": [(380, 90)],
}

_lock = threading.Lock()


def beep(kind: str) -> None:
    pattern = PATTERNS.get(kind)
    if not pattern:
        return
    # Beeps are short; serialise them so overlapping cues don't sound broken.
    with _lock:
        for freq, ms in pattern:
            try:
                winsound.Beep(freq, ms)
            except Exception:  # noqa: BLE001 - no audio device shouldn't break chat
                return


def beep_async(kind: str) -> None:
    threading.Thread(target=beep, args=(kind,), daemon=True).start()
