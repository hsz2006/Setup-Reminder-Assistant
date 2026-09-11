"""Verify actual Windows registration and collision rollback; do not send keypresses."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtWidgets import QApplication
from reminder.hotkeys import Hotkeys, DEFAULTS

qt = QApplication([])
first = Hotkeys(qt, {'toggle': lambda: None, 'capture': lambda: None})
second = Hotkeys(qt, {'toggle': lambda: None, 'capture': lambda: None})
try:
    first.configure(DEFAULTS)
    assert len(first.bindings) == 2
    # Each manager owns a separate ID range in this one test process.
    second.next_id = 0x3100
    conflict_reported = False
    try:
        second.configure(DEFAULTS)
    except ValueError:
        conflict_reported = True
    assert conflict_reported
    assert not second.bindings
    assert len(first.bindings) == 2
    print('Windows global hotkeys registered; collision rejected without affecting original bindings.')
finally:
    first.close()
    second.close()
