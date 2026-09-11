import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from reminder.qt_gui import App
from reminder.hotkeys import Hotkeys, DEFAULTS, parse_hotkey
from reminder.storage import Store


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'gui.sqlite3')
        self.app = App(background=True, store=self.store, bridge_port=0, system_integration=False,
                       clock=lambda: datetime(2026, 9, 16, 16, 10))
        self.app.timer.stop()

    def tearDown(self):
        self.app.shutdown()
        self.app.root.deleteLater()
        self.qt.processEvents()
        self.temp.cleanup()

    def test_dashboard_contains_all_three_sections(self):
        self.app.show()
        self.qt.processEvents()
        for card in (self.app.schedule_card, self.app.tasks_card, self.app.focus_card):
            self.assertTrue(card.isVisible())
        self.assertEqual(self.app.root.centralWidget().objectName(), 'dashboard')

    def test_close_hides_without_stopping_background(self):
        self.app.show()
        self.app.root.close()
        self.qt.processEvents()
        self.assertFalse(self.app.root.isVisible())
        self.assertFalse(self.app.closed)

    def test_meeting_hides_popup_and_blocks_further_popup(self):
        self.app.show()
        popup = self.app.remind('打开书')
        self.qt.processEvents()
        self.assertTrue(popup.isVisible())
        self.assertTrue(popup.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.app.toggle_meeting()
        self.assertFalse(self.app.root.isVisible())
        self.assertFalse(popup.isVisible())
        self.assertIsNone(self.app.remind('不应出现'))
        self.app.toggle_meeting()
        self.assertFalse(self.app.session.meeting)
        self.assertIsNone(self.app.popup)

    def test_quick_capture_saves_to_shared_store(self):
        from PySide6.QtWidgets import QLineEdit, QPushButton
        self.app.quick_capture()
        dialog = self.app.quick_dialog
        dialog.findChild(QLineEdit).setText('打开论文的第一张图')
        next(b for b in dialog.findChildren(QPushButton) if b.text() == '记下').click()
        self.assertEqual(self.store.tasks()[0]['text'], '打开论文的第一张图')

    def test_manual_task_does_not_start_focus(self):
        self.app.task_input.setText('打开书')
        self.app.manual_task()
        self.assertFalse(self.app.focus.current())
        self.assertEqual(self.store.tasks()[0]['text'], '打开书')

    def test_key_validation_and_duplicate_rejection(self):
        self.assertEqual(parse_hotkey('Ctrl+Alt+N')[1:], (3, ord('N')))
        self.app.hotkeys.configure(DEFAULTS)
        previous = dict(self.app.hotkeys.bindings)
        with self.assertRaises(ValueError):
            self.app.hotkeys.configure({'toggle': 'Ctrl+Alt+N', 'capture': 'Ctrl+Alt+N'})
        self.assertEqual(self.app.hotkeys.bindings, previous)
        with self.assertRaises(ValueError):
            parse_hotkey('N')

    def test_settings_has_editable_hotkeys(self):
        from PySide6.QtWidgets import QKeySequenceEdit
        self.app.open_settings()
        editors = self.app.settings_dialog.findChildren(QKeySequenceEdit)
        self.assertEqual(len(editors), 2)


if __name__ == '__main__':
    unittest.main()
