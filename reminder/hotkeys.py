"""Windows global hotkeys. Registration is transactional and reports collisions."""
import ctypes
import os
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtGui import QKeySequence

DEFAULTS = {'toggle': 'Ctrl+Alt+Space', 'capture': 'Ctrl+Alt+N'}


def parse_hotkey(text):
    sequence = QKeySequence(text).toString(QKeySequence.SequenceFormat.PortableText)
    parts = sequence.split('+')
    if ',' in sequence or len(parts) < 2:
        raise ValueError('请设置一个带 Ctrl、Alt 或 Shift 的组合键，不支持连续多组按键。')
    modifiers = {'Ctrl': 2, 'Alt': 1, 'Shift': 4}
    mask = 0
    for part in parts[:-1]:
        if part not in modifiers:
            raise ValueError('支持 Ctrl / Alt / Shift；请勿使用 Windows 键或多组快捷键。')
        mask |= modifiers[part]
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key.upper())
    elif key == 'Space':
        vk = 0x20
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 11:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError('主键请使用字母、数字、空格或 F1—F11。')
    return sequence, mask, vk


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, app, callbacks, native=True):
        super().__init__()
        self.app, self.callbacks = app, callbacks
        self.native = native and os.name == 'nt'
        self.bindings = {}
        self.next_id = 0x2100
        if self.native:
            self.user = ctypes.WinDLL('user32', use_last_error=True)
            self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user.RegisterHotKey.restype = wintypes.BOOL
            self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.app.installNativeEventFilter(self)

    def configure(self, config):
        parsed = {key: parse_hotkey(config[key]) for key in ('toggle', 'capture')}
        if parsed['toggle'][1:] == parsed['capture'][1:]:
            raise ValueError('两个操作不能使用同一组快捷键。')
        if {k: v['text'] for k, v in self.bindings.items()} == {k: v[0] for k, v in parsed.items()}:
            return
        previous = dict(self.bindings)
        self._release()
        proposed = {}
        try:
            for key, (text, mask, vk) in parsed.items():
                self.next_id += 1
                if self.native and not self.user.RegisterHotKey(None, self.next_id, mask | 0x4000, vk):
                    raise ValueError(f'{text} 已被其他程序或系统占用，请更换组合。')
                proposed[key] = {'id': self.next_id, 'text': text, 'mask': mask, 'vk': vk}
        except Exception:
            if self.native:
                for binding in proposed.values():
                    self.user.UnregisterHotKey(None, binding['id'])
            restored = {}
            for key, binding in previous.items():
                if not self.native or self.user.RegisterHotKey(None, binding['id'], binding['mask'] | 0x4000, binding['vk']):
                    restored[key] = binding
            self.bindings = restored
            raise
        self.bindings = proposed

    def _release(self):
        if self.native:
            for binding in self.bindings.values():
                self.user.UnregisterHotKey(None, binding['id'])
        self.bindings = {}

    def close(self):
        self._release()
        if self.native:
            self.app.removeNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if self.native and bytes(event_type) in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:
                for key, binding in self.bindings.items():
                    if msg.wParam == binding['id']:
                        QTimer.singleShot(0, self.callbacks[key])
                        return True, 0
        return False, 0
