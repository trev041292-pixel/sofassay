"""First-run setup: game folder, microphone, talk button, in-game addon."""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import addon_bridge
from .config import load_config, save_config
from .controller import (
    HotkeyTrigger,
    count_button_presses,
    count_hotkey_presses,
    detect_share_button,
)
from .recorder import Recorder, dbfs, input_device_choices, speech_seconds

HOTKEYS = [f"F{i}" for i in range(1, 13)] + ["SPACE", "TAB", "MOUSE4", "MOUSE5"]


class SetupWizard(tk.Toplevel):
    def __init__(self, parent: tk.Misc, on_saved=None):
        super().__init__(parent)
        self.title("WoW Voice Chat - Setup")
        self.resizable(False, False)
        self.transient(parent)
        self.cfg = load_config()
        self.on_saved = on_saved
        self.events: queue.Queue = queue.Queue()
        self.mic_choices: list[tuple[int, str]] = []
        self.busy = False

        self.game_var = tk.StringVar(value=str((self.cfg.get("game") or {}).get("path") or ""))
        self.mic_var = tk.StringVar(value="Windows default input")
        self.mode_var = tk.StringVar(value=self.cfg["trigger"].get("mode", "auto"))
        self.byte_var = tk.StringVar(value=str(self.cfg["trigger"].get("share_byte", 12)))
        self.mask_var = tk.StringVar(value=f"0x{int(self.cfg['trigger'].get('share_mask', 8)):02X}")
        self.hotkey_var = tk.StringVar(value=self.cfg["trigger"].get("hotkey", "F9"))

        self._build()
        self._load_mics()
        if not self.game_var.get().strip():
            self._find_game()
        self._refresh_addon_status()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(100, self._pump)
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=(
                "Three quick checks: game folder, microphone, and talk button. "
                "Most of it is detected for you."
            ),
            font=("Segoe UI", 10),
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        # Game folder ---------------------------------------------------
        game = ttk.LabelFrame(outer, text=" World of Warcraft ", padding=10)
        game.pack(fill="x")
        row = ttk.Frame(game)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.game_var, width=58).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self._browse_game).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Find", command=self._find_game).pack(side="left", padx=(6, 0))
        self.game_status = ttk.Label(game, text="", font=("Segoe UI", 8), wraplength=560,
                                     justify="left")
        self.game_status.pack(anchor="w", pady=(6, 0))

        # Microphone ----------------------------------------------------
        mic = ttk.LabelFrame(outer, text=" Microphone ", padding=10)
        mic.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(mic)
        row.pack(fill="x")
        self.mic_box = ttk.Combobox(row, textvariable=self.mic_var, state="readonly", width=52)
        self.mic_box.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Refresh", width=9, command=self._load_mics).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Test", width=7, command=self._test_mic).pack(side="left", padx=(6, 0))
        self.mic_status = ttk.Label(mic, text="", font=("Segoe UI", 8), wraplength=560,
                                    justify="left")
        self.mic_status.pack(anchor="w", pady=(6, 0))

        # Talk button ---------------------------------------------------
        trigger = ttk.LabelFrame(outer, text=" Talk button ", padding=10)
        trigger.pack(fill="x", pady=(10, 0))

        modes = ttk.Frame(trigger)
        modes.pack(fill="x")
        ttk.Radiobutton(modes, text="Controller button", value="controller",
                        variable=self.mode_var, command=self._update_mode).pack(side="left")
        ttk.Radiobutton(modes, text="Keyboard key", value="hotkey",
                        variable=self.mode_var, command=self._update_mode).pack(side="left", padx=(14, 0))
        ttk.Radiobutton(modes, text="Both", value="auto",
                        variable=self.mode_var, command=self._update_mode).pack(side="left", padx=(14, 0))

        controller_row = ttk.Frame(trigger)
        controller_row.pack(fill="x", pady=(8, 0))
        self.controller_frame = controller_row
        self.detect_btn = ttk.Button(controller_row, text="Detect button", command=self._detect_button)
        self.detect_btn.pack(side="left")
        self.test_btn = ttk.Button(controller_row, text="Test", command=self._test_button)
        self.test_btn.pack(side="left", padx=(6, 0))
        self.controller_summary = ttk.Label(controller_row, text="", font=("Segoe UI", 8),
                                            foreground="#666666")
        self.controller_summary.pack(side="left", padx=(10, 0))

        self.advanced = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            trigger,
            text="Advanced: set the controller byte/bit manually",
            variable=self.advanced,
            command=self._toggle_advanced,
        ).pack(anchor="w", pady=(6, 0))

        self.advanced_row = ttk.Frame(trigger)
        ttk.Label(self.advanced_row, text="Byte").pack(side="left")
        self.byte_spin = ttk.Spinbox(self.advanced_row, from_=0, to=63, width=4,
                                     textvariable=self.byte_var)
        self.byte_spin.pack(side="left", padx=(4, 10))
        ttk.Label(self.advanced_row, text="Bit mask").pack(side="left")
        self.mask_entry = ttk.Entry(self.advanced_row, width=6, textvariable=self.mask_var)
        self.mask_entry.pack(side="left", padx=(4, 10))
        ttk.Button(
            self.advanced_row, text="Reset to Xbox Share", command=self._reset_controller
        ).pack(side="left")

        key_row = ttk.Frame(trigger)
        key_row.pack(fill="x", pady=(8, 0))
        self.key_frame = key_row
        ttk.Label(key_row, text="Key").pack(side="left")
        self.key_box = ttk.Combobox(key_row, textvariable=self.hotkey_var, values=HOTKEYS,
                                    state="readonly", width=10)
        self.key_box.pack(side="left", padx=(4, 10))
        self.test_key_btn = ttk.Button(key_row, text="Test", command=self._test_key)
        self.test_key_btn.pack(side="left")

        self.trigger_status = ttk.Label(
            trigger,
            text=(
                "Xbox controllers already use the Share button. Press Test; if nothing "
                "is detected, press Detect and then press your button three times."
            ),
            font=("Segoe UI", 8),
            wraplength=560,
            justify="left",
        )
        self.trigger_status.pack(anchor="w", pady=(8, 0))

        # Addon ---------------------------------------------------------
        addon = ttk.LabelFrame(outer, text=" In-game panel ", padding=10)
        addon.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(addon)
        row.pack(fill="x")
        self.addon_status = ttk.Label(row, text="", font=("Segoe UI", 8))
        self.addon_status.pack(side="left", anchor="w")
        ttk.Button(row, text="Install / Update", command=self._install_addon).pack(side="right")

        # Footer --------------------------------------------------------
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(14, 0))
        ttk.Label(
            footer,
            text="Restart the tool after saving so the new settings are used.",
            font=("Segoe UI", 8),
            foreground="#666666",
        ).pack(side="left")
        ttk.Button(footer, text="Save & Finish", command=self._save).pack(side="right")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))

        self._update_mode()
        self._update_controller_summary()
        self.byte_var.trace_add("write", lambda *_: self._update_controller_summary())
        self.mask_var.trace_add("write", lambda *_: self._update_controller_summary())
        self._update_game_status()

    # ------------------------------------------------------------------
    def _bg(self, work, done) -> None:
        if self.busy:
            return
        self.busy = True
        self.detect_btn.state(["disabled"])
        self.test_btn.state(["disabled"])
        self.test_key_btn.state(["disabled"])

        def runner() -> None:
            try:
                result = work()
                self.events.put(("done", done, result))
            except Exception as exc:  # noqa: BLE001 - shown in the UI
                self.events.put(("error", None, str(exc)))

        threading.Thread(target=runner, daemon=True).start()

    def _pump(self) -> None:
        try:
            while True:
                try:
                    kind, callback, payload = self.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "error":
                    self._finish_busy()
                    self.trigger_status.configure(text=f"Something went wrong: {payload}")
                elif callback is not None:
                    self._finish_busy()
                    try:
                        callback(payload)
                    except tk.TclError:
                        return
            if self.winfo_exists():
                self.after(100, self._pump)
        except tk.TclError:
            pass

    def _finish_busy(self) -> None:
        self.busy = False
        self.detect_btn.state(["!disabled"])
        self.test_btn.state(["!disabled"])
        self.test_key_btn.state(["!disabled"])

    # ------------------------------------------------------------------
    def _browse_game(self) -> None:
        folder = filedialog.askdirectory(title="Select the World of Warcraft folder",
                                         initialdir=self.game_var.get() or None)
        if folder:
            self.game_var.set(folder)
            self._update_game_status()

    def _find_game(self) -> None:
        found = addon_bridge.detect_game_dir(self.cfg)
        if found:
            self.game_var.set(str(found))
            self._update_game_status()
            self.game_status.configure(text=f"Found: {found}")
        else:
            self.game_status.configure(text="No World of Warcraft folder found - use Browse.")

    def _game_dir(self) -> Path | None:
        raw = self.game_var.get().strip()
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_dir() else None

    def _update_game_status(self) -> None:
        path = self._game_dir()
        if path is None:
            self.game_status.configure(text="Folder not set. Use Find, or Browse to pick it.")
            return
        addons = path / "Interface" / "AddOns"
        if addons.is_dir():
            self.game_status.configure(text=f"AddOns folder found: {addons}")
        else:
            self.game_status.configure(text="This folder has no Interface\\AddOns - is it the right one?")

    # ------------------------------------------------------------------
    def _load_mics(self) -> None:
        self.mic_choices = input_device_choices()
        labels = ["Windows default input"] + [label for _, label in self.mic_choices]
        self.mic_box.configure(values=labels)
        current = self.cfg["audio"].get("input_device")
        if isinstance(current, int):
            for index, label in self.mic_choices:
                if index == current:
                    self.mic_var.set(label)
                    break
            else:
                self.mic_var.set(labels[0])
        elif current:
            for _, label in self.mic_choices:
                if str(current).lower() in label.lower():
                    self.mic_var.set(label)
                    break
            else:
                self.mic_var.set(labels[0])
        else:
            self.mic_var.set(labels[0])
        self.mic_status.configure(text=f"{len(self.mic_choices)} microphone(s) found.")

    def _mic_index(self) -> int | None:
        label = self.mic_var.get()
        for index, name in self.mic_choices:
            if name == label:
                return index
        return None

    def _test_mic(self) -> None:
        index = self._mic_index()
        self.mic_status.configure(text="Recording 2.5 seconds - say something...")
        silence = float(self.cfg["audio"].get("silence_dbfs", -55.0))

        def work():
            recorder = Recorder(device=index)
            recorder.open()
            try:
                recorder.start()
                time.sleep(2.5)
                audio, duration = recorder.stop()
            finally:
                recorder.close()
            return dbfs(audio), speech_seconds(audio, 16000, silence), duration

        def done(result):
            level, voiced, duration = result
            if voiced < 0.2:
                text = f"Heard almost nothing ({level:.0f} dBFS). Check the input level or pick another mic."
            else:
                text = f"Heard {voiced:.1f}s of speech in {duration:.1f}s ({level:.0f} dBFS). Good."
            self.mic_status.configure(text=text)

        self._bg(work, done)

    # ------------------------------------------------------------------
    def _update_mode(self) -> None:
        mode = self.mode_var.get()
        for widget in (self.byte_spin, self.mask_entry, self.detect_btn, self.test_btn):
            widget.state(["!disabled"] if mode in ("auto", "controller") else ["disabled"])
        for widget in (self.key_box, self.test_key_btn):
            widget.state(["!disabled"] if mode in ("auto", "hotkey") else ["disabled"])

    def _toggle_advanced(self) -> None:
        if self.advanced.get():
            self.advanced_row.pack(fill="x", pady=(6, 0))
        else:
            self.advanced_row.pack_forget()

    def _update_controller_summary(self) -> None:
        try:
            byte = int(self.byte_var.get() or 0)
            mask = int(self.mask_var.get() or "0", 16)
        except ValueError:
            self.controller_summary.configure(text="Custom button")
            return
        if byte == 12 and mask == 0x08:
            self.controller_summary.configure(text="Xbox Share default (byte 12, bit 0x08)")
        else:
            self.controller_summary.configure(text=f"Custom button: byte {byte}, bit 0x{mask:02X}")

    def _reset_controller(self) -> None:
        self.byte_var.set("12")
        self.mask_var.set("0x08")
        self.trigger_status.configure(
            text="Reset to the Xbox Share default. Press Test to confirm it still works."
        )

    def _manual_trigger_cfg(self) -> dict:
        cfg = {
            "trigger": {
                "share_byte": int(self.byte_var.get() or 0),
                "share_mask": int(self.mask_var.get() or "0", 16),
                "mode": self.mode_var.get(),
                "hotkey": self.hotkey_var.get(),
            }
        }
        return cfg

    def _detect_button(self) -> None:
        self.trigger_status.configure(
            text="Press the button you want to use 3 times (15 seconds)..."
        )

        def work():
            return detect_share_button(self.cfg, seconds=15.0, target_presses=3, log=lambda *_: None)

        def done(candidates):
            if not candidates:
                self.trigger_status.configure(
                    text="No button detected. Try again, or enter the byte/bit manually."
                )
                return
            best = candidates[0]
            self.byte_var.set(str(best["byte"]))
            self.mask_var.set(f"0x{best['mask']:02X}")
            device = f" on {best['device']}" if best.get("device") else ""
            self.trigger_status.configure(
                text=(
                    f"Detected byte {best['byte']}, bit 0x{best['mask']:02X} "
                    f"({best['presses']} press(es){device}). Click Test to confirm."
                )
            )

        self._bg(work, done)

    def _test_button(self) -> None:
        try:
            cfg = self._manual_trigger_cfg()
        except ValueError:
            self.trigger_status.configure(text="Byte must be 0-63 and the mask must be hex, like 0x08.")
            return
        self.trigger_status.configure(text="Press the configured button a few times (8 seconds)...")

        def work():
            return count_button_presses(cfg, seconds=8.0, log=lambda *_: None)

        def done(presses):
            if presses:
                self.trigger_status.configure(text=f"Detected {presses} press(es). This button works.")
            else:
                self.trigger_status.configure(
                    text="No presses detected. Try Detect, another byte/bit, or the keyboard key instead."
                )

        self._bg(work, done)

    def _test_key(self) -> None:
        key = self.hotkey_var.get()
        self.trigger_status.configure(text=f"Press {key} a few times (6 seconds)...")

        def work():
            return count_hotkey_presses(key, seconds=6.0, log=lambda *_: None)

        def done(presses):
            if presses:
                self.trigger_status.configure(text=f"Detected {presses} {key} press(es). This key works.")
            else:
                self.trigger_status.configure(text=f"{key} was not detected. Try another key.")

        self._bg(work, done)

    # ------------------------------------------------------------------
    def _refresh_addon_status(self) -> None:
        game = self._game_dir()
        installed = bool(game) and (game / "Interface" / "AddOns" / addon_bridge.ADDON_NAME / "WoWVoice.toc").is_file()
        if installed:
            self.addon_status.configure(text="Installed. Type /wvc in game (after /reload) to open it.")
        elif game:
            self.addon_status.configure(text="Not installed yet. Click Install / Update.")
        else:
            self.addon_status.configure(text="Set the game folder first.")

    def _install_addon(self) -> None:
        game = self._game_dir()
        if game is None:
            self.addon_status.configure(text="Set the game folder first.")
            return
        cfg = dict(self.cfg)
        cfg["game"] = dict(cfg.get("game") or {})
        cfg["game"]["path"] = str(game)
        try:
            target = addon_bridge.install_addon(cfg, log=lambda *_: None)
        except PermissionError:
            self.addon_status.configure(
                text=(
                    "Windows blocked the copy. Run setup.bat as administrator once, "
                    f"or copy addon\\{addon_bridge.ADDON_NAME} to "
                    f"{game}\\Interface\\AddOns manually."
                )
            )
            return
        except Exception as exc:  # noqa: BLE001
            self.addon_status.configure(text=f"Could not install: {exc}")
            return
        self._refresh_addon_status()
        self.addon_status.configure(text=f"Installed to {target}. Type /reload in game.")

    # ------------------------------------------------------------------
    def _save(self) -> None:
        game = self._game_dir()
        if game is None:
            messagebox.showerror("WoW Voice Chat", "Pick your World of Warcraft folder first.", parent=self)
            return
        try:
            share_byte = int(self.byte_var.get())
            share_mask = int(self.mask_var.get(), 16)
        except ValueError:
            messagebox.showerror("WoW Voice Chat", "Byte must be a number (0-63) and the mask hex (like 0x08).", parent=self)
            return
        if not 0 <= share_byte <= 63:
            messagebox.showerror("WoW Voice Chat", "Byte must be between 0 and 63.", parent=self)
            return
        if share_mask <= 0 or share_mask > 0xFF or (share_mask & (share_mask - 1)):
            messagebox.showerror("WoW Voice Chat", "The mask must be a single hex bit, like 0x08 or 0x20.", parent=self)
            return
        hotkey = self.hotkey_var.get().strip().upper()
        if HotkeyTrigger(hotkey).vk is None:
            messagebox.showerror("WoW Voice Chat", f"Unknown key: {hotkey}", parent=self)
            return

        cfg = self.cfg
        cfg.setdefault("game", {})
        cfg["game"]["path"] = str(game)
        cfg["game"]["setup_completed"] = True
        cfg.setdefault("audio", {})["input_device"] = self._mic_index()
        cfg.setdefault("trigger", {}).update(
            {
                "mode": self.mode_var.get(),
                "share_byte": share_byte,
                "share_mask": share_mask,
                "hotkey": hotkey,
            }
        )
        save_config(cfg)
        messagebox.showinfo(
            "WoW Voice Chat",
            "Setup saved.\n\nIf the tool is running, restart it so the new microphone and button are used.",
            parent=self,
        )
        if self.on_saved is not None:
            self.on_saved(cfg)
        self.destroy()


def run_setup_wizard(parent: tk.Misc | None = None, on_saved=None) -> None:
    owns_root = parent is None
    root = tk.Tk() if owns_root else None
    if root is not None:
        root.withdraw()
        parent = root
    wizard = SetupWizard(parent, on_saved=on_saved)
    try:
        wizard.wait_window()
    finally:
        if owns_root and root is not None:
            root.destroy()
