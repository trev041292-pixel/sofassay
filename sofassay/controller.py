"""Controller button input via Windows Raw Input.

The Xbox Share button is not exposed by XInput, and this Windows build's
GameInput only provides the legacy interface (which has no Share support).
However controller HID reports *are* delivered through Raw Input, and Raw
Input's ``RIDEV_INPUTSINK`` flag lets us see them while another app (WoW) has
focus.

On the Xbox Wireless Controller tested here the report is 16 bytes and Share
is ``byte 12, bit 0x08``. Both values are configurable, and the setup window
can detect the byte/bit for other controllers.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import queue
import time

from .wowinput import is_key_down

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HWND = wt.HWND
UINT = wt.UINT
LONG_PTR = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LONG_PTR, HWND, UINT, wt.WPARAM, wt.LPARAM)

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEHID = 2
RIDEV_INPUTSINK = 0x00000100
HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GAMEPAD = 0x05
# The button can arrive on the gamepad, joystick, or consumer-control
# collection of the same controller, so listen to all three (as the working
# hardware probe did).
RAW_USAGES = ((HID_USAGE_PAGE_GENERIC, HID_USAGE_GAMEPAD),
              (HID_USAGE_PAGE_GENERIC, 0x04),
              (0x0C, 0x01))

user32.DefWindowProcW.restype = LONG_PTR
user32.DefWindowProcW.argtypes = [HWND, UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassW.argtypes = [ctypes.c_void_p]
user32.CreateWindowExW.restype = HWND
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.DestroyWindow.argtypes = [HWND]
user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
user32.UnregisterClassW.restype = wt.BOOL
user32.RegisterRawInputDevices.argtypes = [ctypes.c_void_p, UINT, UINT]
user32.RegisterRawInputDevices.restype = wt.BOOL
user32.GetRawInputData.argtypes = [
    wt.HANDLE, UINT, wt.LPVOID, ctypes.POINTER(UINT), UINT,
]
user32.GetRawInputData.restype = UINT
user32.GetRawInputDeviceInfoW.argtypes = [
    wt.HANDLE, UINT, wt.LPVOID, ctypes.POINTER(UINT),
]
user32.GetRawInputDeviceInfoW.restype = UINT
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), HWND, UINT, UINT, UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LONG_PTR

kernel32.GetModuleHandleW.restype = wt.HINSTANCE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]

RIDI_DEVICENAME = 0x20000007


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wt.USHORT),
        ("usUsage", wt.USHORT),
        ("dwFlags", wt.DWORD),
        ("hwndTarget", HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wt.DWORD),
        ("dwSize", wt.DWORD),
        ("hDevice", wt.HANDLE),
        ("wParam", wt.WPARAM),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


HEADER_SIZE = ctypes.sizeof(RAWINPUTHEADER)
RAWHID_OFFSET = HEADER_SIZE  # dwSizeHid, dwCount, then the report bytes


class RawInputTrigger:
    """Receives controller HID reports and turns button presses into events."""

    name = "controller button"

    def __init__(self, cfg: dict, log=print, debug: bool = False, capture: bool = False):
        trigger = cfg.get("trigger", {})
        self.share_byte = int(trigger.get("share_byte", 12))
        self.share_mask = int(trigger.get("share_mask", 0x08))
        self.log = log
        self.debug = debug
        self.capture = capture
        self.events: queue.Queue[float] = queue.Queue()
        self.reports: queue.Queue[tuple[int, bytes]] = queue.Queue()
        self.hwnd = None
        self._wndproc = None
        self._class_name = f"SofaSayRawInput{id(self):x}"
        self._pressed: dict[int, bool] = {}
        self._names: dict[int, str] = {}
        self._debug_last: dict[int, bytes] = {}

    # ------------------------------------------------------------------
    def start(self) -> bool:
        hinst = kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._on_message)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            self.log(f"Raw Input: RegisterClass failed (error {ctypes.get_last_error()}).")
            return False

        self.hwnd = user32.CreateWindowExW(
            0, self._class_name, "SofaSay", 0,
            0, 0, 0, 0, None, None, hinst, None,
        )
        if not self.hwnd:
            self.log(f"Raw Input: CreateWindow failed (error {ctypes.get_last_error()}).")
            self._cleanup()
            return False

        devices = (RAWINPUTDEVICE * len(RAW_USAGES))(
            *[
                RAWINPUTDEVICE(page, usage, RIDEV_INPUTSINK, self.hwnd)
                for page, usage in RAW_USAGES
            ]
        )
        ok = user32.RegisterRawInputDevices(
            devices,
            len(RAW_USAGES),
            ctypes.sizeof(RAWINPUTDEVICE),
        )
        if not ok:
            self.log(
                f"Raw Input: could not register the controller "
                f"(error {ctypes.get_last_error()})."
            )
            self._cleanup()
            return False
        return True

    def _cleanup(self) -> None:
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self._class_name:
            user32.UnregisterClassW(self._class_name, kernel32.GetModuleHandleW(None))

    def close(self) -> None:
        self._cleanup()

    # ------------------------------------------------------------------
    def _device_name(self, handle: int) -> str:
        name = self._names.get(handle)
        if name is not None:
            return name
        size = UINT(0)
        user32.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, None, ctypes.byref(size))
        if not size.value:
            name = ""
        else:
            buffer = ctypes.create_unicode_buffer(size.value + 1)
            user32.GetRawInputDeviceInfoW(
                handle, RIDI_DEVICENAME, buffer, ctypes.byref(size)
            )
            name = buffer.value
        self._names[handle] = name
        if name:
            self.log(f"Controller: {name}")
        return name

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            try:
                self._handle_raw(lparam)
            except Exception as exc:  # noqa: BLE001 - never break the message loop
                if self.debug:
                    self.log(f"Raw Input parse error: {exc}")
        # WM_INPUT must go to DefWindowProc so Windows can clean up.
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_raw(self, lparam: int) -> None:
        size = UINT(0)
        user32.GetRawInputData(
            lparam, RID_INPUT, None, ctypes.byref(size), HEADER_SIZE
        )
        if not size.value:
            return
        buffer = ctypes.create_string_buffer(size.value)
        got = user32.GetRawInputData(
            lparam, RID_INPUT, buffer, ctypes.byref(size), HEADER_SIZE
        )
        if got == 0 or got == 0xFFFFFFFF:
            return

        header = RAWINPUTHEADER.from_buffer_copy(buffer.raw[:HEADER_SIZE])
        if header.dwType != RIM_TYPEHID:
            return

        data = buffer.raw
        if len(data) < RAWHID_OFFSET + 8:
            return
        report_size = int.from_bytes(data[RAWHID_OFFSET : RAWHID_OFFSET + 4], "little")
        report_count = int.from_bytes(
            data[RAWHID_OFFSET + 4 : RAWHID_OFFSET + 8], "little"
        )
        if report_size <= 0 or report_count <= 0:
            return

        payload = data[RAWHID_OFFSET + 8 : RAWHID_OFFSET + 8 + report_size * report_count]
        key = int(header.hDevice or 0)

        if self.capture and payload:
            self.reports.put((key, bytes(payload[:report_size])))

        if self.debug:
            previous = self._debug_last.get(key)
            report = payload[:report_size]
            if previous != report:
                self._debug_last[key] = report
                diff = ""
                if previous is not None and len(previous) == len(report):
                    diff = "  changed=" + ",".join(
                        f"{i}:{a:02X}->{b:02X}"
                        for i, (a, b) in enumerate(zip(previous, report))
                        if a != b
                    )
                self.log(f"RAW {len(report)}B {report.hex()}{diff}")

        if len(payload) <= self.share_byte:
            return
        pressed = bool(payload[self.share_byte] & self.share_mask)
        previous = self._pressed.get(key, False)
        self._pressed[key] = pressed
        if pressed and not previous:
            if not self._names.get(key):
                self._device_name(header.hDevice)
            self.events.put(time.monotonic())

    # ------------------------------------------------------------------
    def poll(self) -> list[float]:
        message = wt.MSG()
        while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            if message.message == 0x0012:  # WM_QUIT
                break
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

        found: list[float] = []
        while True:
            try:
                found.append(self.events.get_nowait())
            except queue.Empty:
                return found


def detect_share_button(
    cfg: dict,
    seconds: float = 15.0,
    target_presses: int = 3,
    log=print,
) -> list[dict]:
    """Watch HID reports and rank button candidates.

    A candidate is a single bit in a single byte that goes 0 -> 1 while the
    rest of the report stays the same. Press the wanted button a few times
    during ``seconds``; the most repeated candidate wins.
    """
    trigger = RawInputTrigger(cfg, log=log, capture=True)
    if not trigger.start():
        return []
    previous: dict[tuple[int, int], bytes] = {}
    counts: dict[tuple[int, int, int], int] = {}
    devices: dict[int, str] = {}
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            trigger.poll()
            while True:
                try:
                    key, report = trigger.reports.get_nowait()
                except queue.Empty:
                    break
                signature = (key, len(report))
                before = previous.get(signature)
                previous[signature] = report
                if before is None or len(before) != len(report):
                    continue
                diffs = [
                    (index, before[index] ^ report[index], report[index])
                    for index in range(len(report))
                    if before[index] != report[index]
                ]
                if len(diffs) != 1:
                    continue
                index, changed, new_value = diffs[0]
                if not changed or changed & (changed - 1):
                    continue  # more than one bit changed
                if not (new_value & changed):
                    continue  # release, not press
                candidate = (key, index, changed)
                counts[candidate] = counts.get(candidate, 0) + 1
                if key not in devices:
                    devices[key] = trigger._device_name(key)
            if counts and max(counts.values()) >= target_presses:
                break
            time.sleep(0.005)
    finally:
        trigger.close()

    ranked = [
        {
            "byte": index,
            "mask": mask,
            "presses": presses,
            "device": devices.get(key, ""),
        }
        for (key, index, mask), presses in counts.items()
    ]
    ranked.sort(key=lambda item: (-item["presses"], -item["byte"], item["mask"]))
    return ranked


def count_button_presses(cfg: dict, seconds: float = 8.0, log=print) -> int:
    """Count presses of the currently configured button (for the wizard)."""
    trigger = RawInputTrigger(cfg, log=log)
    if not trigger.start():
        return 0
    presses = 0
    end = time.monotonic() + max(0.5, seconds)
    try:
        while time.monotonic() < end:
            presses += len(trigger.poll())
            time.sleep(0.005)
    finally:
        trigger.close()
    return presses


def count_hotkey_presses(key: str, seconds: float = 6.0, log=print) -> int:
    trigger = HotkeyTrigger(key, log)
    if not trigger.start():
        return 0
    presses = 0
    end = time.monotonic() + max(0.5, seconds)
    while time.monotonic() < end:
        presses += len(trigger.poll())
        time.sleep(0.01)
    return presses


class HotkeyTrigger:
    name = "keyboard hotkey"

    VK = {
        **{f"F{i}": 0x6F + i for i in range(1, 25)},
        "SPACE": 0x20,
        "TAB": 0x09,
        "CAPSLOCK": 0x14,
        "INSERT": 0x2D,
        "DELETE": 0x2E,
        "HOME": 0x24,
        "END": 0x23,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
        "SCROLLLOCK": 0x91,
        "PAUSE": 0x13,
        "NUMLOCK": 0x90,
        "MOUSE4": 0x05,
        "MOUSE5": 0x06,
    }

    def __init__(self, key: str = "F9", log=print):
        self.log = log
        self.key_name = key.upper().strip()
        self.vk = self.VK.get(self.key_name)
        if self.vk is None and len(self.key_name) == 1:
            self.vk = ord(self.key_name)
        self._down = False
        self.name = f"keyboard hotkey ({self.key_name})"

    def start(self) -> bool:
        if self.vk is None:
            self.log(f"Unknown hotkey '{self.key_name}'.")
            return False
        return True

    def poll(self) -> list[float]:
        if self.vk is None:
            return []
        down = is_key_down(self.vk)
        fired = down and not self._down
        self._down = down
        return [time.monotonic()] if fired else []

    def close(self) -> None:
        return


class TriggerManager:
    def __init__(self, cfg: dict, log=print, force_hotkey: bool = False):
        trigger = cfg["trigger"]
        self.cfg = cfg
        self.mode = trigger.get("mode", "auto")
        self.hotkey = trigger.get("hotkey", "F9")
        self.log = log
        self.force_hotkey = force_hotkey
        self.sources: list = []

    def start(self) -> str:
        if self.mode in ("auto", "controller") and not self.force_hotkey:
            share = RawInputTrigger(self.cfg, self.log)
            if share.start():
                self.sources.append(share)
            elif self.mode == "controller":
                self.log("The controller trigger could not start.")

        wants_hotkey = (
            self.mode in ("auto", "hotkey") or self.force_hotkey or not self.sources
        )
        if wants_hotkey:
            hotkey = HotkeyTrigger(self.hotkey, self.log)
            if hotkey.start():
                self.sources.append(hotkey)

        return " + ".join(source.name for source in self.sources) or "none"

    def poll(self) -> list[float]:
        events: list[float] = []
        for source in self.sources:
            events.extend(source.poll())
        return events

    def close(self) -> None:
        for source in self.sources:
            source.close()
