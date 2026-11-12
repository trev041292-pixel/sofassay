"""Configuration defaults that keep the in-game panel in sync."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sofassay.config import DEFAULTS, STOP_PATH  # noqa: E402


class StatusSyncTests(unittest.TestCase):
    def test_sync_status_is_on_by_default(self) -> None:
        self.assertIs(DEFAULTS["addon"]["sync_status"], True)

    def test_announce_status_stays_opt_in(self) -> None:
        self.assertIs(DEFAULTS["addon"]["announce_status"], False)

    def test_stop_file_is_next_to_the_config(self) -> None:
        self.assertEqual(STOP_PATH.name, "sofassay.stop")
        self.assertEqual(STOP_PATH.parent, Path(__file__).resolve().parent.parent)

    def test_panel_auto_start_is_on_by_default(self) -> None:
        self.assertIs(DEFAULTS["panel"]["auto_start"], True)

    def test_panel_always_on_top_stays_off_by_default(self) -> None:
        self.assertIs(DEFAULTS["panel"]["always_on_top"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
