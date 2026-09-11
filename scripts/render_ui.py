"""Render our own Qt widgets offscreen, with disposable sample data for visual QA."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import tempfile
from pathlib import Path
from datetime import datetime
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from reminder.qt_gui import App
from reminder.storage import Store

output = root / 'output' / 'ui'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    store = Store(Path(directory) / 'preview.sqlite3')
    store.add_tasks(['打开上次的科研记录', '读三页图论讲义', '检查一组仿真结果'])
    store.set('allow_draft', 'BV1234567890\nBV0987654321')
    app = App(store=store, bridge_port=0, system_integration=False, clock=lambda: datetime(2026, 9, 16, 8, 30))
    app.timer.stop()
    app.root.resize(1160, 800)
    app.qt.processEvents()
    assert app.root.grab().save(str(output / 'dashboard.png'))
    popup = app.remind('先打开书，看一小段就够了。')
    app.qt.processEvents()
    assert popup.grab().save(str(output / 'reminder.png'))
    popup.accept()
    app.open_settings()
    app.qt.processEvents()
    assert app.settings_dialog.grab().save(str(output / 'shortcuts.png'))
    assets = root / 'assets'
    assets.mkdir(exist_ok=True)
    assert app.icon.pixmap(128, 128).save(str(assets / 'app.ico'), 'ICO')
    app.shutdown()
    app.root.deleteLater()
    app.qt.processEvents()
print(str(output))
