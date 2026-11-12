"""WoW Voice Chat control panel.

A small window that starts and stops the push-to-talk tool without keeping a
console open. It shows the tool's own log live and remembers nothing: closing
the window stops the tool.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

APP_DIR = Path(__file__).resolve().parent
MAIN = APP_DIR / "main.py"
LOG_PATH = APP_DIR / "wow-voicechat.log"
PID_PATH = APP_DIR / "wow-voicechat.pid"

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

COLOR_RUNNING = "#1f8a3b"
COLOR_BUSY = "#b8860b"
COLOR_STOPPED = "#8a8a8a"

WINDOW_TITLE = "WoW Voice Chat"
MUTEX_NAME = "WoWVoiceChat.ControlPanel"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9

kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wt.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def read_pid() -> int | None:
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def clear_pid_file() -> None:
    try:
        PID_PATH.unlink()
    except OSError:
        pass


class ControlPanel(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("660x500")
        self.minsize(560, 420)

        self.proc: subprocess.Popen[str] | None = None
        self.events: queue.Queue[str] = queue.Queue()
        self.recording = False
        self.exit_reported = False
        self.closing = False
        self.tick_job: str | None = None
        self.drain_job: str | None = None

        self._build()
        self._load_log_tail()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.drain_job = self.after(100, self._drain)
        self.tick_job = self.after(300, self._tick)
        self.after(400, self._maybe_first_run)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        style = ttk.Style(self)
        for theme in ("vista", "winnative", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        head = ttk.Frame(outer)
        head.pack(fill="x")
        self.dot = ttk.Label(head, text="\u25cf", font=("Segoe UI", 18))
        self.dot.pack(side="left")
        titles = ttk.Frame(head)
        titles.pack(side="left", padx=(8, 0), fill="x", expand=True)
        ttk.Label(titles, text="WoW Voice Chat", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.detail = ttk.Label(titles, text="Stopped", font=("Segoe UI", 9))
        self.detail.pack(anchor="w")
        self.channel_label = ttk.Label(head, text="Channel: Say", font=("Segoe UI", 9))
        self.channel_label.pack(side="right", anchor="n")

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 10))
        self.start_btn = ttk.Button(buttons, text="Start", command=self.start_app)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop_app)
        self.stop_btn.pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Setup...", command=self.open_setup).pack(side="left", padx=(18, 6))
        ttk.Button(buttons, text="Open config", command=self.open_config).pack(side="left")
        ttk.Button(buttons, text="Clear log", command=self.clear_log).pack(side="left", padx=(6, 0))
        self.topmost = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            buttons, text="Always on top", variable=self.topmost, command=self._toggle_topmost
        ).pack(side="right")

        addon_row = ttk.Frame(outer)
        addon_row.pack(fill="x", pady=(0, 10))
        ttk.Button(
            addon_row, text="Send status to game", command=self.push_status_to_game
        ).pack(side="left")
        ttk.Label(
            addon_row,
            text="Types /wvc status ... so the in-game panel shows the current state.",
            font=("Segoe UI", 8),
            foreground="#666666",
        ).pack(side="left", padx=(8, 0))

        ttk.Label(outer, text="Log", font=("Segoe UI", 9)).pack(anchor="w")
        self.log_view = scrolledtext.ScrolledText(
            outer,
            height=16,
            wrap="word",
            font=("Consolas", 9),
            state="disabled",
            borderwidth=1,
            relief="solid",
        )
        self.log_view.pack(fill="both", expand=True, pady=(2, 8))
        self.log_view.tag_configure("warn", foreground="#b32d2d")
        self.log_view.tag_configure("ok", foreground="#1f8a3b")

        ttk.Label(
            outer,
            text="Press your talk button (Share, or F9) in game to talk. Closing this window stops the tool.",
            font=("Segoe UI", 8),
            foreground="#666666",
        ).pack(anchor="w")

        self.start_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def _set_state(self, text: str, color: str) -> None:
        self.dot.configure(foreground=color)
        self.detail.configure(text=text)

    def _idle_detail(self) -> str:
        if self.recording:
            return "Recording \u2014 press your talk button again to send."
        return "Running \u2014 press your talk button (Share, or F9) to talk."

    @staticmethod
    def _python_exe() -> Path:
        candidate = APP_DIR / ".venv" / "Scripts" / "python.exe"
        if candidate.exists():
            return candidate
        exe = Path(sys.executable)
        if exe.name.lower() == "pythonw.exe":
            alt = exe.with_name("python.exe")
            if alt.exists():
                return alt
        return exe

    def _running_pid(self) -> int | None:
        pid = read_pid()
        if pid is not None and pid_alive(pid):
            return pid
        return None

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------
    def start_app(self) -> None:
        if self._running_pid():
            self._append("Already running.")
            return
        python = self._python_exe()
        if not MAIN.exists():
            messagebox.showerror(WINDOW_TITLE, f"main.py was not found in:\n{APP_DIR}")
            return
        if not python.exists():
            messagebox.showerror(WINDOW_TITLE, f"Python was not found at:\n{python}")
            return

        clear_pid_file()
        self.exit_reported = False
        self.recording = False
        try:
            self.proc = subprocess.Popen(
                [str(python), str(MAIN)],
                cwd=str(APP_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
            )
        except OSError as exc:
            messagebox.showerror(WINDOW_TITLE, f"Could not start the tool:\n{exc}")
            self.proc = None
            return

        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()
        self._append("\u2014 starting WoW Voice Chat \u2014")
        self._set_state("Starting \u2014 loading the speech model\u2026", COLOR_BUSY)
        self.start_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])

    def stop_app(self) -> None:
        pid = self._running_pid()
        if self.proc is not None and self.proc.poll() is None:
            target = self.proc.pid
        else:
            target = pid
        if target is None:
            self.proc = None
            self._set_state("Stopped", COLOR_STOPPED)
            self.start_btn.state(["!disabled"])
            self.stop_btn.state(["disabled"])
            return

        self._append(f"\u2014 stopping (pid {target}) \u2014")
        self._kill_tree(target)
        self.proc = None
        self.recording = False
        self.exit_reported = False
        self._set_state("Stopped", COLOR_STOPPED)
        self.start_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])

    @staticmethod
    def _kill_tree(pid: int) -> None:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    # ------------------------------------------------------------------
    # Background pipes
    # ------------------------------------------------------------------
    def _pump(self, proc: subprocess.Popen[str]) -> None:
        try:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                self.events.put(line.rstrip("\r\n"))
        except (OSError, ValueError):
            pass

    def _drain(self) -> None:
        if self.closing:
            return
        while True:
            try:
                line = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_line(line)
        self.drain_job = self.after(100, self._drain)

    def _handle_line(self, line: str) -> None:
        self._append(line)
        if "Chat channel \u2192" in line:
            self.channel_label.configure(text=f"Channel: {line.split('\u2192', 1)[1].strip()}")
        elif "Sticky channel:" in line:
            self.channel_label.configure(text=f"Channel: {line.split(':', 1)[1].strip()}")
        if "Recording..." in line:
            self.recording = True
        elif (
            "Sending to " in line
            or "Nothing usable was heard" in line
            or "Recording too short" in line
            or "Chat channel \u2192" in line
        ):
            self.recording = False

    def _tick(self, reschedule: bool = True) -> None:
        if self.closing:
            return

        if self.proc is not None:
            code = self.proc.poll()
            if code is not None:
                if not self.exit_reported:
                    self._append(f"\u2014 process exited (code {code}) \u2014")
                    self.exit_reported = True
                self.proc = None

        pid = read_pid()
        if pid is not None and not pid_alive(pid):
            clear_pid_file()
            pid = None

        if pid is not None:
            self._set_state(self._idle_detail(), COLOR_RUNNING)
            self.start_btn.state(["disabled"])
            self.stop_btn.state(["!disabled"])
        elif self.proc is not None:
            self._set_state("Starting \u2014 loading the speech model\u2026", COLOR_BUSY)
            self.start_btn.state(["disabled"])
            self.stop_btn.state(["!disabled"])
        else:
            self._set_state("Stopped", COLOR_STOPPED)
            self.start_btn.state(["!disabled"])
            self.stop_btn.state(["disabled"])

        if reschedule:
            self.tick_job = self.after(800, self._tick)

    # ------------------------------------------------------------------
    # Log view
    # ------------------------------------------------------------------
    def _append(self, line: str) -> None:
        tag = ()
        lowered = line.lower()
        if "could not" in lowered or "error" in lowered or "failed" in lowered:
            tag = ("warn",)
        elif "sending to " in lowered or "chat channel" in lowered:
            tag = ("ok",)
        self.log_view.configure(state="normal")
        self.log_view.insert("end", line + "\n", tag)
        if int(self.log_view.index("end-1c").split(".")[0]) > 1200:
            self.log_view.delete("1.0", "400.0")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _load_log_tail(self, lines: int = 120) -> None:
        if not LOG_PATH.exists():
            return
        try:
            text = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        if not text:
            return
        self._append("\u2014 previous log \u2014")
        for line in text[-lines:]:
            self._append(line)

    def clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    # ------------------------------------------------------------------
    # Setup / in-game addon
    # ------------------------------------------------------------------
    def _maybe_first_run(self) -> None:
        if self.closing:
            return
        try:
            from wowvoice.config import load_config

            cfg = load_config()
        except (SystemExit, OSError, ValueError):
            return
        game = cfg.get("game") or {}
        if not game.get("show_wizard_until_complete", True):
            return
        if game.get("setup_completed"):
            return
        self._append("\u2014 first run: opening setup \u2014")
        self.open_setup()

    def open_setup(self) -> None:
        try:
            from wowvoice.setup_wizard import SetupWizard
        except Exception as exc:  # noqa: BLE001 - show the real reason
            messagebox.showerror(WINDOW_TITLE, f"Could not open the setup window:\n{exc}")
            return
        SetupWizard(self, on_saved=self._after_setup_saved)

    def _after_setup_saved(self, cfg: dict) -> None:
        game = (cfg.get("game") or {}).get("path")
        if game:
            self._append(f"Setup saved. Game folder: {game}")
        if self._running_pid():
            if messagebox.askyesno(
                WINDOW_TITLE,
                "Setup saved.\n\nRestart the tool now so the new microphone and button are used?",
            ):
                self.stop_app()
                self.after(600, self.start_app)

    def push_status_to_game(self) -> None:
        self._append("Sending status to the in-game panel...")
        threading.Thread(target=self._push_status_worker, daemon=True).start()

    def _push_status_worker(self) -> None:
        try:
            from wowvoice import addon_bridge
            from wowvoice.config import load_config
            from wowvoice.recorder import Recorder

            cfg = load_config()
            cfg.setdefault("addon", {})["enabled"] = True
            state = "running" if self._running_pid() else "stopped"
            chat = cfg.get("chat") or {}
            name = str(chat.get("default_channel", "say"))
            labels = {
                channel.get("name"): channel.get("label", channel.get("name", name))
                for channel in chat.get("channels", [])
            }
            mic = Recorder((cfg.get("audio") or {}).get("input_device")).description
            text = addon_bridge.build_status(
                f"state={state}",
                f"channel={labels.get(name, name.title())}",
                f"mic={mic}",
            )
            ok = addon_bridge.push_status(cfg, text, log=lambda *_: None)
        except Exception as exc:  # noqa: BLE001 - reported in the log view
            self.events.put(f"Could not send status: {exc}")
            return
        self.events.put(
            "Status sent to the in-game panel."
            if ok
            else "Status was not sent - is World of Warcraft running?"
        )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def open_config(self) -> None:
        path = APP_DIR / "config.json"
        if not path.exists():
            messagebox.showinfo(WINDOW_TITLE, "config.json is created the first time you start the tool.")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(WINDOW_TITLE, f"Could not open config.json:\n{exc}")

    def _toggle_topmost(self) -> None:
        self.attributes("-topmost", self.topmost.get())

    def _on_close(self) -> None:
        if self._running_pid() and not messagebox.askyesno(
            WINDOW_TITLE, "Stop WoW Voice Chat and close this window?"
        ):
            return
        self.closing = True
        for job in (self.tick_job, self.drain_job):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self.stop_app()
        self.destroy()


def existing_panel() -> bool:
    """True when another panel is already open (and focuses it)."""
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
        return False
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    return True


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    if existing_panel():
        return 0
    ControlPanel().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
