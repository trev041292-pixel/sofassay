"""Command-line entry point for SofaSay."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from sofassay import wowinput
from sofassay.app import PID_PATH, SofaSayApp
from sofassay.config import CONFIG_PATH, load_config
from sofassay.controller import RawInputTrigger, TriggerManager
from sofassay.recorder import Recorder, describe_device, list_input_devices


def show_devices(cfg: dict) -> None:
    print("Audio input devices:")
    print(list_input_devices())
    print()
    try:
        index = Recorder(cfg["audio"]["input_device"]).resolve_device()
        print(f"Selected input  : {describe_device(index)}")
    except Exception as exc:  # noqa: BLE001
        print(f"Selected input  : unavailable ({exc})")
    print(f"Hotkey fallback : {cfg['trigger']['hotkey']}")
    print(
        "Controller     : "
        f"byte {cfg['trigger']['share_byte']}, "
        f"mask 0x{int(cfg['trigger']['share_mask']):02X}"
    )
    trigger = RawInputTrigger(cfg)
    if trigger.start():
        print("Controller      : ready (Windows Raw Input)")
        trigger.close()
    else:
        print("Controller      : Raw Input registration failed")


def test_trigger(cfg: dict, seconds: int = 30) -> None:
    manager = TriggerManager(cfg)
    print(f"Trigger sources: {manager.start()}")
    print(f"Press the controller button (or the hotkey) for {seconds} seconds...")
    end = time.time() + seconds
    try:
        while time.time() < end:
            for _ in manager.poll():
                print("TRIGGER", flush=True)
            time.sleep(0.01)
    finally:
        manager.close()


def raw_debug(cfg: dict, seconds: int = 30) -> None:
    trigger = RawInputTrigger(cfg, debug=True)
    if not trigger.start():
        return
    print(f"Showing raw controller reports for {seconds} seconds.")
    print("Press the controller button once and watch which byte/bit changes.")
    end = time.time() + seconds
    try:
        while time.time() < end:
            trigger.poll()
            time.sleep(0.005)
    finally:
        trigger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Push-to-talk chat for World of Warcraft")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="config file path")
    parser.add_argument("--devices", action="store_true", help="list microphones and check the controller")
    parser.add_argument("--trigger-test", action="store_true", help="test the button/hotkey without loading the speech model")
    parser.add_argument("--raw-debug", action="store_true", help="show raw controller reports (for other controllers)")
    parser.add_argument("--dry-run", action="store_true", help="transcribe but print the chat line instead of sending it")
    parser.add_argument("--hotkey-only", action="store_true", help="ignore the controller and use only the keyboard hotkey")
    parser.add_argument("--send-test", metavar="TEXT", help="send a fixed chat line to WoW (use with --dry-run to preview)")
    parser.add_argument("--setup", action="store_true", help="open the first-run setup window (mic, button, addon)")
    parser.add_argument("--seconds", type=int, default=30, help="duration for the test modes (default 30)")
    args = parser.parse_args()

    if args.setup:
        from sofassay.setup_wizard import run_setup_wizard

        run_setup_wizard()
        return 0

    cfg = load_config(args.config)

    if args.devices:
        show_devices(cfg)
        return 0
    if args.raw_debug:
        raw_debug(cfg, args.seconds)
        return 0
    if args.trigger_test:
        test_trigger(cfg, args.seconds)
        return 0
    if args.send_test:
        ok = wowinput.send_chat(args.send_test, cfg, dry_run=args.dry_run)
        return 0 if ok else 1

    app = SofaSayApp(cfg, dry_run=args.dry_run, hotkey_only=args.hotkey_only)
    try:
        PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    try:
        return app.run()
    finally:
        try:
            if PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
