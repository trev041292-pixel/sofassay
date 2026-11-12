"""Local speech-to-text using faster-whisper on CPU."""
from __future__ import annotations

import os
import re
import time

import numpy as np

from .recorder import dbfs, speech_seconds, trim_silence

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Whisper likes to invent these on silence / breath noise.
_HALLUCINATIONS = {
    "you",
    "thank you",
    "thanks",
    "thanks for watching",
    "thank you for watching",
    "bye",
    "bye bye",
    "okay",
    "ok",
    "uh",
    "um",
    "hmm",
    "please subscribe",
    "subtitles by the amara.org community",
}


def clean_transcript(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\s+", " ", text).strip()
    # Drop stray leading/trailing dash or quote artefacts.
    return text.strip(" \t\r\n\"'-")


class Transcriber:
    def __init__(self, cfg: dict, log=print):
        stt = cfg["stt"]
        self.model_name = stt["model"]
        self.device = stt["device"]
        self.compute_type = stt["compute_type"]
        self.language = stt["language"] or None
        self.beam_size = int(stt["beam_size"])
        self.model_dir = stt.get("model_dir") or None
        self.silence_dbfs = float(cfg["audio"]["silence_dbfs"])
        self.log = log
        self.model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel

        started = time.monotonic()
        self.log(
            f"Loading speech model '{self.model_name}' "
            f"(first run downloads it, this can take a few minutes)..."
        )
        self.model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            download_root=self.model_dir,
        )
        self.log(f"Speech model ready in {time.monotonic() - started:.1f}s")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str, float]:
        """Return (text, speech_duration). Empty text means nothing usable was heard."""
        if self.model is None:
            raise RuntimeError("Speech model is not loaded.")

        audio = trim_silence(audio, sample_rate, self.silence_dbfs)
        if audio.size == 0:
            return "", 0.0
        voiced = speech_seconds(audio, sample_rate, self.silence_dbfs)
        peak = dbfs(audio)
        if voiced < 0.12 or peak < self.silence_dbfs:
            return "", voiced

        started = time.monotonic()
        segments, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            best_of=self.beam_size,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            without_timestamps=True,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
        )
        parts: list[str] = []
        for seg in segments:
            if getattr(seg, "no_speech_prob", 0.0) and seg.no_speech_prob > 0.8:
                continue
            parts.append(seg.text)
        text = clean_transcript(" ".join(parts))
        elapsed = time.monotonic() - started

        if text.lower().strip(" .!?,") in _HALLUCINATIONS and voiced < 1.0:
            self.log(f'Ignored likely hallucination: "{text}"')
            return "", voiced
        if not re.search(r"[a-zA-Z0-9]", text):
            return "", voiced

        self.log(f"Transcribed in {elapsed:.1f}s ({voiced:.1f}s of speech): \"{text}\"")
        return text, voiced
