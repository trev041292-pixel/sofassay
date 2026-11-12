"""Window focus, clipboard, and synthetic keyboard input for WoW."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

DWORD = wt.DWORD
WORD = wt.WORD
LONG = ctypes.c_long
ULONG_PTR = ctypes.c_size_t
HWND = wt.HWND
UINT = wt.UINT

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_V = 0x56

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
GA_ROOT = 2


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", DWORD),
        ("wParamL", WORD),
        ("wParamH", WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("u", INPUT_UNION)]


user32.SendInput.argtypes = [UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = UINT
user32.MapVirtualKeyW.argtypes = [UINT, UINT]
user32.MapVirtualKeyW.restype = UINT

user32.GetWindowTextLengthW.argtypes = [HWND]
user32.GetWindowTextW.argtypes = [HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [HWND, wt.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [HWND]
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(DWORD)]
user32.GetForegroundWindow.restype = HWND
user32.GetAncestor.argtypes = [HWND, UINT]
user32.GetAncestor.restype = HWND
user32.IsIconic.argtypes = [HWND]
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.BringWindowToTop.argtypes = [HWND]
user32.SetForegroundWindow.argtypes = [HWND]
user32.SetFocus.argtypes = [HWND]
user32.AttachThreadInput.argtypes = [DWORD, DWORD, wt.BOOL]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

kernel32.GetCurrentThreadId.restype = DWORD
kernel32.OpenProcess.argtypes = [DWORD, wt.BOOL, DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE,
    DWORD,
    wt.LPWSTR,
    ctypes.POINTER(DWORD),
]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.GlobalAlloc.argtypes = [UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalFree.argtypes = [wt.HGLOBAL]

user32.OpenClipboard.argtypes = [HWND]
user32.EmptyClipboard.argtypes = []
user32.CloseClipboard.argtypes = []
user32.SetClipboardData.argtypes = [UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE
user32.GetClipboardData.argtypes = [UINT]
user32.GetClipboardData.restype = wt.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [UINT]
user32.IsClipboardFormatAvailable.restype = wt.BOOL

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, HWND, wt.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL


# --------------------------------------------------------------------------
# Keyboard
# --------------------------------------------------------------------------
def _scan_code(vk: int) -> int:
    return int(user32.MapVirtualKeyW(vk, 0))


def _key_event(vk: int, up: bool = False) -> None:
    scan = _scan_code(vk)
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    event = INPUT(type=INPUT_KEYBOARD)
    event.u.ki = KEYBDINPUT(0, scan, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def tap_key(vk: int, hold_ms: int = 12) -> None:
    _key_event(vk, False)
    time.sleep(hold_ms / 1000.0)
    _key_event(vk, True)


def paste_keys() -> None:
    _key_event(VK_CONTROL, False)
    time.sleep(0.010)
    _key_event(VK_V, False)
    time.sleep(0.012)
    _key_event(VK_V, True)
    time.sleep(0.008)
    _key_event(VK_CONTROL, True)


def _unicode_event(unit: int, up: bool = False) -> None:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    event = INPUT(type=INPUT_KEYBOARD)
    event.u.ki = KEYBDINPUT(0, unit, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def type_text(text: str, char_delay_ms: float = 2.0) -> None:
    """Type ``text`` as Unicode characters, without touching modifiers.

    Clipboard paste was leaving Ctrl held from WoW's point of view, which made
    the final Enter behave as Ctrl+Enter (send but keep the chat box open).
    """
    data = text.encode("utf-16-le")
    for index in range(0, len(data), 2):
        unit = int.from_bytes(data[index : index + 2], "little")
        _unicode_event(unit, False)
        _unicode_event(unit, True)
        if char_delay_ms:
            time.sleep(char_delay_ms / 1000.0)


def is_key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


# --------------------------------------------------------------------------
# Clipboard
# --------------------------------------------------------------------------
def get_clipboard_text() -> str | None:
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    opened = False
    for _ in range(6):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.04)
    if not opened:
        return False
    try:
        user32.EmptyClipboard()
        size = (len(text) + 1) * ctypes.sizeof(ctypes.c_wchar)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        try:
            source = ctypes.create_unicode_buffer(text)
            ctypes.memmove(pointer, source, size)
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
def _window_title(hwnd: HWND) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_class(hwnd: HWND) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _process_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return Path(buffer.value).name
    finally:
        kernel32.CloseHandle(handle)


def find_wow_window(process_name: str = "Wow.exe", title_hint: str = "") -> HWND | None:
    wanted = process_name.lower()
    best: tuple[int, HWND] | None = None

    def callback(hwnd, _lparam):
        nonlocal best
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return True
        if _process_name(pid.value).lower() != wanted:
            return True
        title = _window_title(hwnd)
        if not title:
            return True
        score = 0
        if title_hint and title_hint.lower() in title.lower():
            score += 2
        if _window_class(hwnd).startswith("GxWindowClass"):
            score += 3
        if score > 0:
            if best is None or score > best[0]:
                best = (score, hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return best[1] if best else None


def foreground_root() -> HWND | None:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    return user32.GetAncestor(hwnd, GA_ROOT) or hwnd


def is_foreground(hwnd: HWND) -> bool:
    return foreground_root() == hwnd


def focus_window(hwnd: HWND) -> bool:
    if is_foreground(hwnd):
        return True
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    try:
        if fg_thread and fg_thread != current_thread:
            attached = bool(user32.AttachThreadInput(current_thread, fg_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, fg_thread, False)
    time.sleep(0.08)
    return is_foreground(hwnd)


def send_chat(
    text: str,
    cfg: dict,
    log=print,
    process_name: str = "Wow.exe",
    title_hint: str = "World of Warcraft",
    dry_run: bool = False,
    close_chat: bool | None = None,
) -> bool:
    """Open WoW chat, enter ``text``, and submit it.

    ``close_chat`` overrides the configured Escape step. Slash commands close
    the edit box by themselves, so posting an addon command passes ``False``.
    """
    chat = cfg["chat"]
    if dry_run:
        log(f"[dry run] {text}")
        return True

    hwnd = find_wow_window(process_name, title_hint)
    if not hwnd:
        log(f"Could not find the WoW window ({process_name}). Is the game running?")
        return False
    if not is_foreground(hwnd):
        if chat.get("focus_wow", True):
            if not focus_window(hwnd):
                log("Could not bring WoW to the foreground.")
                return False
        else:
            log("WoW is not the foreground window, so the message was not sent.")
            return False

    mode = chat.get("input_mode", "type")
    if mode == "paste":
        previous = get_clipboard_text() if chat.get("restore_clipboard", True) else None
        if not set_clipboard_text(text):
            log("Could not write to the Windows clipboard.")
            return False
        time.sleep(0.03)

        tap_key(VK_RETURN)
        time.sleep(chat.get("open_delay_ms", 300) / 1000.0)
        paste_keys()
        time.sleep(chat.get("paste_delay_ms", 400) / 1000.0)
        tap_key(VK_RETURN)
        time.sleep(chat.get("send_delay_ms", 200) / 1000.0)

        if chat.get("restore_clipboard", True) and previous is not None:
            time.sleep(0.15)
            set_clipboard_text(previous)
        _close_chat(chat, close_chat)
        return True

    tap_key(VK_RETURN)
    time.sleep(chat.get("open_delay_ms", 300) / 1000.0)
    type_text(text, float(chat.get("type_delay_ms", 2.0)))
    time.sleep(chat.get("paste_delay_ms", 400) / 1000.0)
    tap_key(VK_RETURN)
    time.sleep(chat.get("send_delay_ms", 200) / 1000.0)
    _close_chat(chat, close_chat)
    return True


def _close_chat(chat: dict, override: bool | None = None) -> None:
    """Dismiss the edit box after sending.

    This client keeps the chat box open after a synthetic Enter, so a stray
    Escape is normal here. Disable ``close_chat_after_send`` if your setup
    closes the box by itself (Escape would then open the game menu).
    """
    enabled = chat.get("close_chat_after_send", True) if override is None else override
    if not enabled:
        return
    time.sleep(chat.get("close_delay_ms", 150) / 1000.0)
    tap_key(VK_ESCAPE)
    time.sleep(chat.get("close_settle_ms", 80) / 1000.0)
