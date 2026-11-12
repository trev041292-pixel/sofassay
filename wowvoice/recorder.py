"""Microphone recording with device-rate resampling to 16 kHz.

The input stream stays open while the app runs; frames are only kept between
``start()`` and ``stop()``. Opening the stream up front avoids the ~100-300 ms
device warm-up that would otherwise clip the first word after the beep.
"""
from __future__ import annotations

import threading
import time

import numpy as np

try:
    import sounddevice as sd
except Exception as exc:  # pragma: no cover - import-time hardware failure
    sd = None
    _SD_ERROR = exc


def list_input_devices() -> str:
    if sd is None:
        return f"sounddevice unavailable: {_SD_ERROR}"
    try:
        default_in = sd.default.device[0]
    except Exception:  # noqa: BLE001
        default_in = None
    lines = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) < 1:
            continue
        marker = " (default)" if idx == default_in else ""
        lines.append(
            f"[{idx:2d}] {dev['name']}{marker}  "
            f"channels={dev['max_input_channels']}  rate={int(dev['default_samplerate'])}"
        )
    return "\n".join(lines) or "No input devices found."


def dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))) + 1e-12)
    return 20.0 * np.log10(rms)


def frame_levels(samples: np.ndarray, sample_rate: int, frame_ms: int = 20) -> np.ndarray:
    frame = max(1, int(sample_rate * frame_ms / 1000))
    usable = len(samples) - (len(samples) % frame)
    if usable < frame:
        return np.array([dbfs(samples)], dtype=np.float32)
    blocks = samples[:usable].reshape(-1, frame)
    rms = np.sqrt(np.mean(np.square(blocks, dtype=np.float64), axis=1) + 1e-12)
    return (20.0 * np.log10(rms)).astype(np.float32)


def trim_silence(
    samples: np.ndarray,
    sample_rate: int,
    threshold_dbfs: float = -55.0,
    pad_ms: int = 120,
) -> np.ndarray:
    """Trim leading/trailing silence, keeping a little padding."""
    if samples.size == 0:
        return samples
    levels = frame_levels(samples, sample_rate)
    active = np.flatnonzero(levels >= threshold_dbfs)
    if active.size == 0:
        return np.zeros(0, dtype=np.float32)
    frame = max(1, int(sample_rate * 0.020))
    start = max(0, int(active[0]) * frame - int(sample_rate * pad_ms / 1000))
    end = min(
        len(samples),
        (int(active[-1]) + 1) * frame + int(sample_rate * pad_ms / 1000),
    )
    return samples[start:end].astype(np.float32, copy=False)


def speech_seconds(samples: np.ndarray, sample_rate: int, threshold_dbfs: float) -> float:
    levels = frame_levels(samples, sample_rate)
    return float(np.count_nonzero(levels >= threshold_dbfs)) * 0.020


def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    count = int(round(samples.size * dst_rate / src_rate))
    if count <= 1:
        return np.zeros(0, dtype=np.float32)
    # Linear interpolation is plenty for speech ASR and needs no extra deps.
    x_old = np.linspace(0.0, 1.0, num=samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=count, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def describe_device(index: int) -> str:
    if sd is None:
        return str(index)
    try:
        info = sd.query_devices(index)
        api = sd.query_hostapis(info["hostapi"])["name"]
        return f"{info['name']} ({api})"
    except Exception:  # noqa: BLE001
        return str(index)


def input_device_choices() -> list[tuple[int, str]]:
    """[(index, label)] for every microphone Windows exposes."""
    if sd is None:
        return []
    choices: list[tuple[int, str]] = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) < 1:
            continue
        choices.append((idx, describe_device(idx)))
    return choices


class Recorder:
    def __init__(self, device=None, target_rate: int = 16000):
        self.device = device
        self.target_rate = target_rate
        self._frames: list[np.ndarray] = []
        self._stream = None
        self._device_index: int | None = None
        self._capture_rate = target_rate
        self._lock = threading.Lock()
        self._active = threading.Event()
        self._started_at = 0.0

    def resolve_device(self) -> int:
        """Turn ``audio.input_device`` into one concrete device index."""
        if sd is None:
            raise RuntimeError(f"sounddevice unavailable: {_SD_ERROR}")
        if self.device is None:
            try:
                index = sd.default.device[0]
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"No default input device: {exc}") from exc
            if index is None or index < 0:
                raise RuntimeError("No default input device.")
            return index
        if isinstance(self.device, int):
            return self.device

        needle = str(self.device).lower()
        matches = [
            dev
            for dev in sd.query_devices()
            if dev.get("max_input_channels", 0) > 0
            and needle in dev["name"].lower()
        ]
        if not matches:
            raise RuntimeError(f"No microphone matching '{self.device}'.")
        if len(matches) == 1:
            return matches[0]["index"]

        # Windows lists one microphone under MME, DirectSound, WASAPI and
        # WDM-KS. Prefer the default host API (usually MME) because it is the
        # most forgiving about sample rates and channel counts.
        hostapis = sd.query_hostapis()
        try:
            default_api = sd.default.hostapi
        except Exception:  # noqa: BLE001
            default_api = None

        def rank(dev: dict) -> int:
            api = hostapis[dev["hostapi"]]["name"].lower()
            if dev["hostapi"] == default_api:
                return 0
            if "mme" in api:
                return 1
            if "wasapi" in api:
                return 2
            if "directsound" in api:
                return 3
            return 4

        return min(matches, key=rank)["index"]

    @property
    def description(self) -> str:
        if self._device_index is not None:
            return describe_device(self._device_index)
        return str(self.device) if self.device is not None else "Windows default input"

    def _pick_rate(self, device: int) -> int | None:
        try:
            info = sd.query_devices(device, "input")
            native = int(round(info["default_samplerate"]))
        except Exception:  # noqa: BLE001
            native = self.target_rate
        candidates = [self.target_rate]
        if native not in candidates:
            candidates.append(native)
        for rate in candidates:
            try:
                sd.check_input_settings(
                    device=device, channels=1, dtype="float32", samplerate=rate
                )
                return rate
            except Exception:  # noqa: BLE001
                continue
        return None

    def _callback(self, indata, frames, time_info, status):  # noqa: ANN001
        del frames, time_info, status
        if not self._active.is_set():
            return
        with self._lock:
            self._frames.append(indata[:, 0].copy())

    def open(self) -> None:
        """Open the microphone once and keep it warm."""
        if self._stream is not None:
            return
        if sd is None:
            raise RuntimeError(f"sounddevice unavailable: {_SD_ERROR}")
        index = self.resolve_device()
        rate = self._pick_rate(index)
        if rate is None:
            raise RuntimeError(
                f"The microphone '{describe_device(index)}' does not support mono "
                "float32 recording."
            )
        stream = sd.InputStream(
            device=index,
            channels=1,
            samplerate=rate,
            dtype="float32",
            latency="low",
            callback=self._callback,
        )
        stream.start()
        self._stream = stream
        self._device_index = index
        self._capture_rate = rate

    def start(self) -> None:
        self.open()
        with self._lock:
            self._frames = []
        self._started_at = time.monotonic()
        self._active.set()

    def stop(self) -> tuple[np.ndarray, int]:
        """Stop capturing and return (mono float32 at 16 kHz, duration seconds)."""
        self._active.clear()
        with self._lock:
            frames = self._frames
            self._frames = []
        if not frames:
            return np.zeros(0, dtype=np.float32), 0.0
        audio = np.concatenate(frames).astype(np.float32, copy=False)
        duration = audio.size / self._capture_rate
        return resample(audio, self._capture_rate, self.target_rate), duration

    def close(self) -> None:
        self._active.clear()
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started_at if self._active.is_set() else 0.0
