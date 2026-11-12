"""Checks for the SavedVariables parser and the addon settings bridge."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wowvoice import addon_bridge  # noqa: E402

SAMPLE = r'''
-- SavedVariables written by the game
WoWVoiceDB = {
	["defaultChannel"] = "party",
	["sticky"] = false,
	["closeChatAfterSend"] = false,
	["maxChars"] = 200,
	["inputMode"] = "type",
	["status"] = "state=running | channel=Party | mic=PRO X",
	["statusTime"] = 1770000000,
	["x"] = -120,
	["y"] = 40,
	["version"] = 1,
	["nested"] = {
		["a"] = 1,
		"positional",
		["deep"] = { true, false, nil },
	},
}
'''

BASE_CFG = {
    "chat": {
        "default_channel": "say",
        "sticky": True,
        "close_chat_after_send": True,
        "input_mode": "type",
        "max_message_chars": 250,
        "channels": [
            {"name": "say", "command": "/s"},
            {"name": "party", "command": "/p"},
        ],
    }
}


class ParseTests(unittest.TestCase):
    def test_parses_settings(self) -> None:
        data = addon_bridge.parse_savedvars(SAMPLE)
        self.assertEqual(data["defaultChannel"], "party")
        self.assertIs(data["sticky"], False)
        self.assertEqual(data["maxChars"], 200)
        self.assertEqual(data["x"], -120)
        self.assertEqual(data["nested"]["a"], 1)
        self.assertEqual(data["nested"]["1"], "positional")
        self.assertIs(data["nested"]["deep"]["1"], True)

    def test_escapes_and_comments(self) -> None:
        text = 'WoWVoiceDB = { -- start\n ["s"] = "a \\"quote\\" and \\\\ slash",\n ["n"] = 1.5, }'
        data = addon_bridge.parse_savedvars(text)
        self.assertEqual(data["s"], 'a "quote" and \\ slash')
        self.assertEqual(data["n"], 1.5)

    def test_missing_root(self) -> None:
        with self.assertRaises(ValueError):
            addon_bridge.parse_savedvars("SomethingElse = {}")


class ApplyTests(unittest.TestCase):
    def test_applies_known_settings(self) -> None:
        data = addon_bridge.parse_savedvars(SAMPLE)
        cfg = {"chat": dict(BASE_CFG["chat"])}
        changes = addon_bridge.apply_settings(cfg, data)
        self.assertEqual(cfg["chat"]["default_channel"], "party")
        self.assertIs(cfg["chat"]["sticky"], False)
        self.assertIs(cfg["chat"]["close_chat_after_send"], False)
        self.assertEqual(cfg["chat"]["max_message_chars"], 200)
        self.assertEqual(len(changes), 4)

    def test_ignores_unknown_channel(self) -> None:
        cfg = {"chat": dict(BASE_CFG["chat"])}
        addon_bridge.apply_settings(cfg, {"defaultChannel": "trade chat"})
        self.assertEqual(cfg["chat"]["default_channel"], "say")

    def test_ignores_unknown_keys(self) -> None:
        cfg = {"chat": dict(BASE_CFG["chat"])}
        changes = addon_bridge.apply_settings(cfg, {"nonsense": 1, "status": "x"})
        self.assertEqual(changes, [])

    def test_status_line(self) -> None:
        text = addon_bridge.build_status("state=running", "channel=Party", "")
        self.assertEqual(text, "state=running | channel=Party")
        self.assertLessEqual(len(addon_bridge.build_status("x" * 400)), 180)


class WatcherTests(unittest.TestCase):
    def test_picks_up_file_created_later(self) -> None:
        cfg = {"chat": dict(BASE_CFG["chat"])}
        watcher = addon_bridge.SettingsWatcher(cfg, interval=0.5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "WoWVoice.lua"
            with mock.patch.object(addon_bridge, "find_savedvars", return_value=path):
                self.assertEqual(watcher.poll_once(), [])
                path.write_text(SAMPLE, encoding="utf-8")
                changes = watcher.poll_once()
                self.assertIn("default_channel = party", changes)
                self.assertIs(cfg["chat"]["sticky"], False)
                self.assertEqual(watcher.poll_once(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
