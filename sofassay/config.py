"""Configuration loading/saving for SofaSay."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
# The control panel asks a running tool to shut down gracefully by creating
# this file. The tool then pushes a final "stopped" status to the addon.
STOP_PATH = APP_DIR / "sofassay.stop"

# Channel definitions. ``command`` is pasted in front of the message. The
# whisper entry is special: its command contains {target}. The spoken alias
# list is matched at the start of every utterance ("party hey there").
DEFAULT_CHANNELS = [
    {
        "name": "say",
        "label": "Say",
        "command": "/s",
        "aliases": ["say", "say chat", "s", "local"],
    },
    {
        "name": "party",
        "label": "Party",
        "command": "/p",
        "aliases": ["party", "party chat", "p", "group"],
    },
    {
        "name": "yell",
        "label": "Yell",
        "command": "/y",
        "aliases": ["yell", "yell chat", "y", "shout"],
    },
    {
        "name": "guild",
        "label": "Guild",
        "command": "/g",
        "aliases": ["guild", "guild chat", "g"],
    },
    {
        "name": "officer",
        "label": "Officer",
        "command": "/o",
        "aliases": ["officer", "officer chat", "o"],
    },
    {
        "name": "raid",
        "label": "Raid",
        "command": "/raid",
        "aliases": ["raid", "raid chat"],
    },
    {
        "name": "raidwarning",
        "label": "Raid Warning",
        "command": "/rw",
        "aliases": ["raid warning", "raid warn", "rw"],
    },
    {
        "name": "instance",
        "label": "Instance",
        "command": "/i",
        "aliases": ["instance", "instance chat", "dungeon"],
    },
    {
        "name": "general",
        "label": "General",
        "command": "/1",
        "aliases": ["general", "general chat", "gen"],
    },
    {
        "name": "trade",
        "label": "Trade",
        "command": "/2",
        "aliases": ["trade", "trade chat"],
    },
    {
        "name": "localdefense",
        "label": "Local Defense",
        "command": "/3",
        "aliases": ["local defense", "local defence", "defense", "defence"],
    },
    {
        "name": "lfg",
        "label": "Looking for Group",
        "command": "/4",
        "aliases": ["looking for group", "lfg", "looking for dungeon", "lfd"],
    },
    {
        "name": "worlddefense",
        "label": "World Defense",
        "command": "/5",
        "aliases": ["world defense", "world defence", "worlddefense"],
    },
    {
        "name": "whisper",
        "label": "Whisper",
        "command": "/w {target}",
        "aliases": ["whisper", "whisper to", "w", "tell", "dm", "pm"],
        "needs_target": True,
    },
    {
        "name": "reply",
        "label": "Reply",
        "command": "/r",
        "aliases": ["reply", "respond", "answer"],
    },
    {
        "name": "emote",
        "label": "Emote",
        "command": "/e",
        "aliases": ["emote", "emote chat"],
    },
]

DEFAULTS = {
    "trigger": {
        # auto = Share button, plus the hotkey as a fallback.
        # controller = Share button only. hotkey = keyboard only.
        "mode": "auto",
        "hotkey": "F9",
        # Xbox Wireless Controller HID layout: report byte 12, bit 0x08.
        # Change these only if `--raw-debug` shows Share somewhere else.
        "share_byte": 12,
        "share_mask": 8,
    },
    "audio": {
        "input_device": None,          # null = Windows default mic; or index/name
        "sample_rate": 16000,
        "max_record_seconds": 30,
        "min_record_seconds": 0.35,
        "start_delay_ms": 60,
        "silence_dbfs": -55.0,
    },
    "stt": {
        "model": "small.en",           # tiny.en / base.en / small.en / distil-small.en
        "device": "cpu",               # cpu (reliable) or cuda
        "compute_type": "int8",        # int8 for cpu, float16 for cuda
        "language": "en",
        "beam_size": 5,
        "model_dir": None,
    },
    "addon": {
        # The bundled in-game panel (addon/SofaSay).
        "enabled": True,
        # Let the addon's saved settings override config.json (applied at
        # startup and whenever the game writes SavedVariables).
        "use_in_game_settings": True,
        "watch_seconds": 2.0,
        # Tell the in-game panel when the tool starts and stops, so it does not
        # keep showing an old state. This types "/sofa status ..." into the game
        # once at startup and once on shutdown.
        "sync_status": True,
        # Send the in-game panel a status update after every message.
        "announce_status": False,
    },
    "panel": {
        # Start listening as soon as the control panel opens.
        "auto_start": True,
        # Keep the control panel above the game.
        "always_on_top": False,
    },
    "game": {
        # Auto-detected by the setup wizard; null = search common folders.
        "path": None,
        # Show the first-run setup wizard until it has been completed once.
        "show_wizard_until_complete": True,
        "setup_completed": False,
    },
    "chat": {
        "default_channel": "say",
        "sticky": True,
        "sticky_whisper": True,
        "focus_wow": True,
        "window_process": "Wow.exe",
        "window_title": "World of Warcraft",
        # "type" types the text directly (no Ctrl involved); "paste" uses the
        # clipboard. Typing is the default because the game can keep Ctrl
        # logically held after a synthetic paste, leaving chat open.
        "input_mode": "type",
        "type_delay_ms": 2,
        "open_delay_ms": 300,
        "paste_delay_ms": 400,
        "send_delay_ms": 200,
        # This client keeps the chat box open after a synthetic Enter, so send
        # a single Escape to dismiss it. Turn this off if your box closes on
        # its own (Escape would otherwise open the game menu).
        "close_chat_after_send": True,
        "close_delay_ms": 150,
        "close_settle_ms": 80,
        "restore_clipboard": True,
        "max_message_chars": 250,
        "channels": DEFAULT_CHANNELS,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, keeping unknown user keys."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> dict:
    path = path or CONFIG_PATH
    user: dict = {}
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"Could not read {path}: {exc}") from exc
    cfg = _deep_merge(DEFAULTS, user)
    if not path.exists():
        save_config(cfg, path)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def channel_by_name(cfg: dict, name: str) -> dict | None:
    for ch in cfg["chat"]["channels"]:
        if ch["name"] == name:
            return ch
    return None
