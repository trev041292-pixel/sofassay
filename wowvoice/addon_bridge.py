"""Bridge to the in-game WoWVoice addon.

AddOns in this client cannot open sockets or files, so the two sides talk
through the only channels the game offers:

* addon -> tool: the addon's SavedVariables file (written by the game on
  ``/reload`` or logout), which we parse here;
* tool -> addon: a slash command typed into the chat box (``/wvc status ...``).

Nothing here requires the addon to be installed; callers simply get no
settings back.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from .wowinput import send_chat

ADDON_NAME = "WoWVoice"
SAVEDVARS_FILE = f"{ADDON_NAME}.lua"
ADDON_VERSION = "1.0.4"

# Addon key -> (config section, config key, converter)
SETTING_MAP = {
    "defaultChannel": ("chat", "default_channel", str),
    "sticky": ("chat", "sticky", bool),
    "closeChatAfterSend": ("chat", "close_chat_after_send", bool),
    "inputMode": ("chat", "input_mode", str),
    "maxChars": ("chat", "max_message_chars", int),
}


# --------------------------------------------------------------------------
# WoW folders
# --------------------------------------------------------------------------
def _candidate_roots(cfg: dict | None = None) -> list[Path]:
    roots: list[Path] = []
    if cfg:
        configured = (cfg.get("game") or {}).get("path")
        if configured:
            roots.append(Path(configured))

    bases = [
        Path(r"C:\Program Files (x86)\World of Warcraft"),
        Path(r"C:\Program Files\World of Warcraft"),
        Path(r"C:\World of Warcraft"),
        Path(r"D:\World of Warcraft"),
        Path(r"E:\World of Warcraft"),
    ]
    for base in bases:
        roots.append(base)
        roots.append(base / "_forever_")
        roots.append(base / "_classic_era_")
        roots.append(base / "_retail_")

    try:
        import winreg

        for hive, key in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\World of Warcraft"),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    value, _ = winreg.QueryValueEx(handle, "InstallPath")
                    if value:
                        roots.append(Path(value))
            except OSError:
                continue
    except ImportError:
        pass

    return roots


def detect_game_dir(cfg: dict | None = None) -> Path | None:
    """Find a WoW folder that contains ``Interface/AddOns``."""
    seen: set[str] = set()
    for root in _candidate_roots(cfg):
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        addons = resolved / "Interface" / "AddOns"
        if addons.is_dir():
            return resolved
        if resolved.is_dir():
            for child in resolved.iterdir():
                addons = child / "Interface" / "AddOns"
                if addons.is_dir():
                    return child
    return None


def find_savedvars(cfg: dict | None = None) -> Path | None:
    """Newest ``WoWVoice.lua`` across every account on the machine."""
    game = detect_game_dir(cfg)
    if game is None:
        return None
    candidates = list(game.glob("WTF/Account/*/SavedVariables/" + SAVEDVARS_FILE))
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda path: path.stat().st_mtime_ns)
    except OSError:
        return candidates[0]


# --------------------------------------------------------------------------
# Minimal Lua table parser (SavedVariables are plain ``WoWVoiceDB = { ... }``)
# --------------------------------------------------------------------------
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class _LuaTableParser:
    def __init__(self, text: str, start: int = 0):
        self.text = text
        self.i = start

    def error(self, message: str) -> ValueError:
        return ValueError(f"{message} at offset {self.i}")

    def skip(self) -> None:
        text = self.text
        while self.i < len(text):
            ch = text[self.i]
            if ch in " \t\r\n":
                self.i += 1
            elif text.startswith("--[[", self.i):
                end = text.find("]]", self.i + 4)
                self.i = len(text) if end < 0 else end + 2
            elif text.startswith("--", self.i):
                end = text.find("\n", self.i)
                self.i = len(text) if end < 0 else end + 1
            else:
                break

    def peek(self) -> str:
        return self.text[self.i] if self.i < len(self.text) else ""

    def expect(self, char: str) -> None:
        self.skip()
        if self.peek() != char:
            raise self.error(f"expected {char!r}")
        self.i += 1

    def parse_string(self) -> str:
        quote = self.text[self.i]
        self.i += 1
        out: list[str] = []
        while self.i < len(self.text):
            ch = self.text[self.i]
            if ch == quote:
                self.i += 1
                return "".join(out)
            if ch != "\\":
                out.append(ch)
                self.i += 1
                continue
            self.i += 1
            if self.i >= len(self.text):
                break
            esc = self.text[self.i]
            self.i += 1
            if esc == "n":
                out.append("\n")
            elif esc == "t":
                out.append("\t")
            elif esc == "r":
                out.append("\r")
            elif esc.isdigit():
                digits = esc
                while len(digits) < 3 and self.i < len(self.text) and self.text[self.i].isdigit():
                    digits += self.text[self.i]
                    self.i += 1
                out.append(chr(int(digits)))
            else:
                out.append(esc)
        raise self.error("unterminated string")

    def parse_value(self):
        self.skip()
        ch = self.peek()
        if ch == "{":
            return self.parse_table()
        if ch in "\"'":
            return self.parse_string()
        match = _NUMBER_RE.match(self.text, self.i)
        if match and match.group(0):
            self.i = match.end()
            raw = match.group(0)
            return float(raw) if any(c in raw for c in ".eE") else int(raw)
        match = _IDENT_RE.match(self.text, self.i)
        if match:
            self.i = match.end()
            word = match.group(0)
            if word == "true":
                return True
            if word == "false":
                return False
            if word == "nil":
                return None
            raise self.error(f"unexpected identifier {word!r}")
        raise self.error(f"unexpected character {ch!r}")

    def parse_table(self) -> dict:
        self.expect("{")
        result: dict = {}
        index = 1
        while True:
            self.skip()
            ch = self.peek()
            if ch == "}":
                self.i += 1
                return result
            if ch == "[":
                self.i += 1
                key = self.parse_value()
                self.expect("]")
                self.expect("=")
                result[str(key)] = self.parse_value()
            else:
                save = self.i
                match = _IDENT_RE.match(self.text, self.i)
                if match:
                    self.i = match.end()
                    word = match.group(0)
                    self.skip()
                    if self.peek() == "=":
                        self.i += 1
                        result[word] = self.parse_value()
                    else:
                        self.i = save
                        result[str(index)] = self.parse_value()
                        index += 1
                else:
                    result[str(index)] = self.parse_value()
                    index += 1
            self.skip()
            ch = self.peek()
            if ch == ",":
                self.i += 1
            elif ch == "}":
                self.i += 1
                return result
            else:
                raise self.error("expected ',' or '}'")


def parse_savedvars(text: str, root: str = "WoWVoiceDB") -> dict:
    match = re.search(rf"\b{root}\s*=\s*", text)
    if not match:
        raise ValueError(f"{root} was not found in the SavedVariables file")
    parser = _LuaTableParser(text, match.end())
    data = parser.parse_value()
    if not isinstance(data, dict):
        raise ValueError("SavedVariables root is not a table")
    return data


def load_settings(cfg: dict | None = None) -> tuple[dict, Path | None]:
    """Return (addon settings, file) or ({}, None) when unavailable."""
    path = find_savedvars(cfg)
    if path is None:
        return {}, None
    try:
        data = parse_savedvars(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}, path
    return data, path


def apply_settings(cfg: dict, data: dict) -> list[str]:
    """Copy known addon values into ``cfg`` and describe what changed."""
    changes: list[str] = []
    chat = cfg.setdefault("chat", {})
    for addon_key, (section, key, convert) in SETTING_MAP.items():
        if addon_key not in data:
            continue
        raw = data[addon_key]
        try:
            value = convert(raw)
        except (TypeError, ValueError):
            continue
        if key == "default_channel":
            value = str(value).strip().lower().replace(" ", "")
            names = {ch["name"] for ch in chat.get("channels", [])}
            if value not in names:
                continue
        target = cfg.setdefault(section, {})
        if target.get(key) != value:
            changes.append(f"{key} = {value}")
            target[key] = value
    return changes


# --------------------------------------------------------------------------
# Live watcher: applies in-game changes after the next /reload
# --------------------------------------------------------------------------
class SettingsWatcher(threading.Thread):
    def __init__(self, cfg: dict, on_change=None, log=print, interval: float = 2.0):
        super().__init__(daemon=True, name="addon-settings-watcher")
        self.cfg = cfg
        self.on_change = on_change
        self.log = log
        self.interval = max(0.5, float(interval))
        self.stopped = threading.Event()
        self._signature = None

    def stop(self) -> None:
        self.stopped.set()

    def run(self) -> None:
        while not self.stopped.wait(self.interval):
            self.poll_once()

    def poll_once(self) -> list[str]:
        path = find_savedvars(self.cfg)
        if path is None:
            return []
        try:
            stat = path.stat()
        except OSError:
            return []
        signature = (str(path), stat.st_mtime_ns, stat.st_size)
        if signature == self._signature:
            return []
        self._signature = signature
        try:
            data = parse_savedvars(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as exc:
            self.log(f"In-game settings could not be read: {exc}")
            return []
        changes = apply_settings(self.cfg, data)
        if changes:
            self.log("In-game settings applied: " + ", ".join(changes))
            if self.on_change is not None:
                try:
                    self.on_change(self.cfg, changes)
                except Exception as exc:  # noqa: BLE001 - watcher must not die
                    self.log(f"In-game settings could not be applied: {exc}")
        return changes


# --------------------------------------------------------------------------
# Talking to the addon
# --------------------------------------------------------------------------
def trigger_label(cfg: dict) -> str:
    """Short, human-readable name for the configured talk button."""
    trigger = cfg.get("trigger") or {}
    mode = str(trigger.get("mode", "auto")).lower()
    hotkey = str(trigger.get("hotkey", "F9"))
    if mode == "hotkey":
        return hotkey
    if mode == "controller":
        return "Controller"
    return f"Controller + {hotkey}"


def build_status(*parts: str) -> str:
    """Join ``key=value`` parts; values must not contain separators."""
    clean: list[str] = []
    for part in parts:
        if not part:
            continue
        clean.append(str(part).replace("|", "/").replace("\n", " ").strip())
    return " | ".join(clean)[:180]


def catch_up_due(announce: bool, synced: bool) -> bool:
    """True when a sent message should trigger a one-off status refresh.

    Starting the tool before the game means the startup status never reached
    the addon, and nothing retries it. The first message that goes through
    proves the player is in the world, so it is a safe moment to catch up.
    A blinking WoW window is not: at the login screen typed text can land in
    the account fields.

    When ``announce`` is on the panel already updates after every message.
    """
    return not announce and not synced


def push_status(cfg: dict, text: str, log=print) -> bool:
    """Type ``/wvc status ...`` into the game.

    Slash commands close the chat box on their own, so no Escape is sent.
    """
    if not (cfg.get("addon") or {}).get("enabled", True):
        return False
    line = f"/wvc status {text}".strip()
    return send_chat(line, cfg, log=log, close_chat=False)


# --------------------------------------------------------------------------
# Installing the addon
# --------------------------------------------------------------------------
def addon_source_dir() -> Path:
    from .config import APP_DIR

    return APP_DIR / "addon" / ADDON_NAME


def addon_installed(game_dir: Path | None = None) -> bool:
    game = game_dir or detect_game_dir()
    if game is None:
        return False
    return (game / "Interface" / "AddOns" / ADDON_NAME / f"{ADDON_NAME}.toc").is_file()


def install_addon(cfg: dict, log=print) -> Path:
    """Copy the bundled addon into the game's AddOns folder."""
    game = detect_game_dir(cfg)
    if game is None:
        raise FileNotFoundError("Could not find the World of Warcraft folder.")
    source = addon_source_dir()
    if not source.is_dir():
        raise FileNotFoundError(f"The bundled addon is missing: {source}")
    target = game / "Interface" / "AddOns" / ADDON_NAME
    target.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        if item.is_dir():
            continue
        destination = target / item.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.read_bytes())
    log(f"AddOn installed: {target}")
    return target
