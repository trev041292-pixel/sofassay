"""Main push-to-talk state machine."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

from . import beeps, wowinput
from . import addon_bridge
from .config import APP_DIR
from .controller import TriggerManager
from .recorder import Recorder
from .routing import Router
from .transcriber import Transcriber

LOG_PATH = APP_DIR / "wow-voicechat.log"
PID_PATH = APP_DIR / "wow-voicechat.pid"


class VoiceChatApp:
    def __init__(self, cfg: dict, dry_run: bool = False, hotkey_only: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.log_path = LOG_PATH
        self.recorder = Recorder(
            device=cfg["audio"].get("input_device"),
            target_rate=int(cfg["audio"].get("sample_rate", 16000)),
        )
        self.transcriber = Transcriber(cfg, log=self.log)
        self.router = Router(cfg, log=self.log)
        self.triggers = TriggerManager(cfg, log=self.log, force_hotkey=hotkey_only)
        self.recording = False
        self.worker: threading.Thread | None = None
        self.stopping = threading.Event()
        self._last_trigger = 0.0
        self.addon_watcher: addon_bridge.SettingsWatcher | None = None

    # ------------------------------------------------------------------
    def log(self, message: str) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {message}"
        print(line, flush=True)
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    def _banner(self, trigger_names: str) -> None:
        mic_name = self.recorder.description
        print()
        print("=" * 66)
        print("  WoW Voice Chat")
        print("=" * 66)
        print(f"  Trigger       : {trigger_names}")
        print(f"  Microphone    : {mic_name}")
        print(f"  Speech model  : {self.cfg['stt']['model']}")
        print(f"  Sticky channel: {self.router.describe()}")
        print(f"  Dry run       : {'yes (nothing is sent to WoW)' if self.dry_run else 'no'}")
        print()
        print("  Press the Capture/Share button (or F9) to start talking.")
        print("  Press it again to stop, transcribe, and send.")
        print("  Ctrl+C quits.")
        print("=" * 66)
        print()

    # ------------------------------------------------------------------
    def run(self) -> int:
        try:
            self.transcriber.load()
        except Exception as exc:  # noqa: BLE001
            self.log(f"Could not load the speech model: {exc}")
            return 1

        try:
            self.recorder.open()
        except Exception as exc:  # noqa: BLE001
            self.log(f"Could not open the microphone: {exc}")
            self.log("Run with --devices to see available microphones.")
            return 1

        trigger_names = self.triggers.start()
        if trigger_names == "none":
            self.log("No input trigger available. Connect the Xbox controller or set trigger.mode to 'hotkey'.")
            return 1

        self._start_addon_watcher()
        self._banner(trigger_names)
        self._push_status_on_start()

        try:
            while not self.stopping.is_set():
                for _ in self.triggers.poll():
                    self._on_trigger()
                if self.recording:
                    limit = float(self.cfg["audio"]["max_record_seconds"])
                    if self.recorder.elapsed >= limit:
                        self.log(f"Maximum recording length ({limit:.0f}s) reached.")
                        self._stop_recording()
                time.sleep(0.008)
        except KeyboardInterrupt:
            self.log("Shutting down.")
        finally:
            if self.addon_watcher is not None:
                self.addon_watcher.stop()
            if self.recording:
                try:
                    self.recorder.stop()
                except Exception:  # noqa: BLE001
                    pass
            self.triggers.close()
            self.recorder.close()
        return 0

    def stop(self) -> None:
        self.stopping.set()

    # ------------------------------------------------------------------
    # In-game addon bridge
    # ------------------------------------------------------------------
    def _start_addon_watcher(self) -> None:
        options = self.cfg.get("addon") or {}
        if not options.get("enabled", True) or not options.get("use_in_game_settings", True):
            return
        saved = addon_bridge.find_savedvars(self.cfg)
        self.addon_watcher = addon_bridge.SettingsWatcher(
            self.cfg,
            on_change=self._on_addon_settings,
            log=self.log,
            interval=float(options.get("watch_seconds", 2.0)),
        )
        self.addon_watcher.poll_once()
        self.addon_watcher.start()
        if saved is None:
            self.log(
                "In-game addon: no saved settings yet; watching for the file "
                "(install the addon, then /reload in game)."
            )
        else:
            self.log("In-game settings: watching the WoWVoice addon.")

    def _on_addon_settings(self, cfg: dict, changes: list[str]) -> None:
        chat = cfg.get("chat", {})
        self.router.sticky = bool(chat.get("sticky", self.router.sticky))
        self.router.max_chars = int(chat.get("max_message_chars", self.router.max_chars))
        if any(change.startswith("default_channel") for change in changes):
            channel = self.router.find_channel(chat.get("default_channel", ""))
            if channel:
                self.router.default_channel = channel
                self.router.current = channel
                self.log(f"In-game channel → {channel.get('label', channel['name'])}")

    def _status_parts(self, state: str = "running", last: str | None = None) -> list[str]:
        parts = [f"state={state}"]
        parts.append(f"channel={self.router.describe()}")
        mic = self.recorder.description or ""
        if mic:
            parts.append(f"mic={mic[:44]}")
        if last:
            parts.append(f"last={last[:90]}")
        return parts

    def _push_status_on_start(self) -> None:
        if not (self.cfg.get("addon") or {}).get("push_status_on_start"):
            return
        addon_bridge.push_status(
            self.cfg,
            addon_bridge.build_status(*self._status_parts()),
            log=self.log,
        )

    # ------------------------------------------------------------------
    def _on_trigger(self) -> None:
        now = time.monotonic()
        if now - self._last_trigger < 0.35:
            return
        self._last_trigger = now

        if self.worker is not None and self.worker.is_alive():
            self.log("Still transcribing the previous message...")
            beeps.beep("busy")
            return

        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        beeps.beep("start")
        time.sleep(float(self.cfg["audio"].get("start_delay_ms", 220)) / 1000.0)
        try:
            self.recorder.start()
        except Exception as exc:  # noqa: BLE001
            self.log(f"Could not start recording: {exc}")
            beeps.beep("error")
            return
        self.recording = True
        self.log("Recording... (press Capture again to send)")

    def _stop_recording(self) -> None:
        self.recording = False
        try:
            audio, duration = self.recorder.stop()
        except Exception as exc:  # noqa: BLE001
            self.log(f"Could not stop recording: {exc}")
            beeps.beep("error")
            return

        beeps.beep("stop")
        minimum = float(self.cfg["audio"].get("min_record_seconds", 0.35))
        if duration < minimum:
            self.log(f"Recording too short ({duration:.2f}s); ignored.")
            beeps.beep("error")
            return

        self.log(f"Recorded {duration:.1f}s. Transcribing...")
        self.worker = threading.Thread(target=self._process, args=(audio,), daemon=True)
        self.worker.start()

    # ------------------------------------------------------------------
    def _process(self, audio) -> None:  # noqa: ANN001
        try:
            text, _voiced = self.transcriber.transcribe(audio)
            if not text:
                self.log("Nothing usable was heard.")
                beeps.beep("error")
                return

            routed = self.router.parse(text)
            if routed is None:
                self.log("Could not work out what to do with that.")
                beeps.beep("error")
                return

            if not routed.body:
                self.log(f"Chat channel → {routed.label}")
                beeps.beep("channel")
                return

            self.log(f'Sending to {routed.label}: "{routed.body}"')
            ok = wowinput.send_chat(
                routed.command,
                self.cfg,
                log=self.log,
                dry_run=self.dry_run,
            )
            if ok:
                beeps.beep("sent")
                if (self.cfg.get("addon") or {}).get("announce_status"):
                    addon_bridge.push_status(
                        self.cfg,
                        addon_bridge.build_status(*self._status_parts(last=routed.body)),
                        log=self.log,
                    )
            else:
                beeps.beep("error")
        except Exception as exc:  # noqa: BLE001
            self.log(f"Error while handling the message: {exc}")
            beeps.beep("error")
