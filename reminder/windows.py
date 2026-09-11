"""Receive real Windows lock/unlock and suspend/resume events on a hidden window."""
import ctypes
from ctypes import wintypes
import os
import threading
import time


def listen(events):
    if os.name != 'nt':
        return
    def worker():
        user = ctypes.WinDLL('user32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        wts = ctypes.WinDLL('wtsapi32', use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        PROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.DefWindowProcW.restype = LRESULT
        locked = None
        suspended = None

        @PROC
        def proc(hwnd, msg, wp, lp):
            nonlocal locked, suspended
            if msg == 0x02B1:
                if wp == 7:
                    locked = time.time()
                    events.put(('locked', True))
                elif wp == 8:
                    events.put(('locked', False))
                    events.put(('unlock', time.time() - locked if locked is not None else 0))
                    locked = None
            if msg == 0x0218:
                if wp == 4:
                    suspended = time.time()
                    events.put(('suspend', True))
                elif wp in (7, 18) and suspended is not None:
                    events.put(('resume', time.time() - suspended))
                    suspended = None
            return user.DefWindowProcW(hwnd, msg, wp, lp)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', PROC), ('cbClsExtra', ctypes.c_int),
                        ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
                        ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HBRUSH),
                        ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR)]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        instance = kernel.GetModuleHandleW(None)
        cls = WNDCLASS()
        cls.lpfnWndProc, cls.hInstance, cls.lpszClassName = proc, instance, 'StudyStartEvents'
        user.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
        user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
            wintypes.HINSTANCE, wintypes.LPVOID]
        user.CreateWindowExW.restype = wintypes.HWND
        if not user.RegisterClassW(ctypes.byref(cls)):
            events.put(('error', '无法注册 Windows 事件窗口。'))
            return
        hwnd = user.CreateWindowExW(0, cls.lpszClassName, '', 0, 0, 0, 0, 0, None, None, instance, None)
        wts.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
        if not hwnd or not wts.WTSRegisterSessionNotification(hwnd, 0):
            events.put(('error', '无法监听锁屏事件；定时提醒仍可用。'))
            return
        events.put(('windows_ready', True))
        msg = wintypes.MSG()
        while user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user.TranslateMessage(ctypes.byref(msg))
            user.DispatchMessageW(ctypes.byref(msg))
    threading.Thread(target=worker, daemon=True).start()
