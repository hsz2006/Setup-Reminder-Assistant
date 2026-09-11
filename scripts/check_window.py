"""Native regression: recover from SW_HIDE, tray-close and minimization."""
import ctypes
import os
import subprocess
import sys
import tempfile
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

if __name__ == '__main__':
    if len(sys.argv) == 1:
        with tempfile.TemporaryDirectory() as directory:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            env = dict(os.environ, QT_QPA_PLATFORM='windows')
            result = subprocess.run([sys.executable, __file__, directory], startupinfo=startup, env=env, timeout=30)
            raise SystemExit(result.returncode)
    from ctypes import wintypes
    from reminder.qt_gui import App
    from reminder.storage import Store
    app = App(background=True, store=Store(Path(sys.argv[1]) / 'test.sqlite3'),
              bridge_port=0, system_integration=False)
    app.timer.stop()
    user32 = ctypes.WinDLL('user32')
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    def visible():
        app.qt.processEvents()
        return bool(user32.IsWindowVisible(int(app.root.winId())))
    try:
        assert not visible(), 'Background startup unexpectedly visible'
        app.show()
        assert visible(), 'First show failed after hidden launch'
        app.root.close()
        assert not visible(), 'Close should hide to tray'
        app.events.put(('show', None))
        app.tick()
        assert visible(), 'Second launch event failed to restore window'
        app.root.showMinimized()
        app.qt.processEvents()
        app.show()
        assert visible() and not user32.IsIconic(int(app.root.winId())), 'Restore from minimization failed'
        print('PASS: native hidden startup, first show, close/reopen, minimize/restore')
    finally:
        app.shutdown()
        app.root.deleteLater()
        app.qt.processEvents()
