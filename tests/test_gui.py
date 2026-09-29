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

    def test_focus_allowlist_is_read_only_video_page(self):
        from PySide6.QtWidgets import QTextEdit, QPushButton
        from reminder.allowed_videos import AllowedVideos
        self.store.set('video_titles', {'BV1234567890': '测试课程'})
        self.app.focus.start(40, 'BV1234567890')
        self.store.set('allow_draft', '')
        self.app.edit_allowlist()
        page = self.app.allow_dialog.findChild(AllowedVideos)
        self.assertIsNotNone(page)
        self.assertEqual(page.labels['BV1234567890'].text(), '测试课程')
        self.assertIsNone(self.app.allow_dialog.findChild(QTextEdit))
        self.assertEqual([b.text() for b in page.findChildren(QPushButton)], ['Edge 打开'])
        self.app.refresh()
        self.assertIn('1', self.app.allow_button.text())
        self.app.allow_dialog.reject()
        self.assertTrue(page.stopped.is_set())

    def test_bili_lock_keeps_reminders_and_personal_focus_independent(self):
        import time
        now = time.time()
        self.app.clock = lambda: datetime.fromtimestamp(now)
        popup = self.app.remind(bili=True)
        self.app.bridge.usage.last = self.app.bridge.usage.last_bili = now
        self.app.bridge.usage.seconds = 1800
        self.app.tick()
        self.assertTrue(popup.isVisible())
        self.assertFalse(self.app.focus.current(now))
        current = self.app.focus.bili_lock(now)
        self.assertGreater(current['end'], now)
        self.assertEqual(current['allow'], [])
        self.assertTrue(self.app.start_button.isEnabled())
        self.assertTrue(self.app.minutes.isEnabled())
        self.assertIn('已锁定', self.app.status.text())
        self.app.quit()
        self.assertFalse(self.app.closed)
        self.assertEqual(self.app.focus.bili_lock(now)['id'], current['id'])

    def test_bili_warning_reuses_actions_and_does_not_start_focus(self):
        from PySide6.QtWidgets import QLabel, QPushButton
        from reminder.bili_usage import WARNING
        popup = self.app.remind(bili=True)
        self.assertEqual(popup.findChild(QLabel, 'biliWarning').text(), WARNING)
        action = popup.findChild(QLabel, 'heroText')
        previous = action.text()
        next(b for b in popup.findChildren(QPushButton) if b.text() == '换一步').click()
        self.assertNotEqual(action.text(), previous)
        self.assertEqual(self.store.get('bili_last_action'), action.text())
        self.assertFalse(self.app.focus.current())
        next(b for b in popup.findChildren(QPushButton) if b.text() == '暂缓 5 分钟').click()
        self.assertFalse(popup.isVisible())

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

    def test_switch_single_task_changes_without_completing_it(self):
        from PySide6.QtWidgets import QLabel, QPushButton
        self.store.add_tasks(['阅读MATLAB仿真代码'])
        popup = self.app.remind()
        action = popup.findChild(QLabel, 'heroText')
        self.assertEqual(action.text(), '阅读MATLAB仿真代码')
        switch = next(b for b in popup.findChildren(QPushButton) if b.text() == '换一步')
        for _ in range(12):
            previous = action.text()
            switch.click()
            self.assertNotEqual(action.text(), previous)
        self.assertEqual(len(self.store.tasks()), 1)
        self.assertFalse(self.app.focus.current())
        labels = [item.text() for item in popup.findChildren(QLabel)]
        self.assertIn('做到这一步就可以停下。是否继续，由你决定。', labels)
        self.assertNotIn('打开书，看一小段就够了。想继续时再继续。', labels)

    def test_snooze_closes_popup_sets_five_minutes_without_focus(self):
        from PySide6.QtWidgets import QPushButton
        popup = self.app.remind()
        next(b for b in popup.findChildren(QPushButton) if b.text() == '暂缓 5 分钟').click()
        self.assertFalse(popup.isVisible())
        self.assertIsNone(self.app.popup)
        self.assertEqual(self.store.get('snooze_end'), self.app.clock().timestamp() + 300)
        self.assertFalse(self.app.focus.current())
        self.assertFalse(self.store.get('rest_end', 0))

    def test_settings_has_editable_hotkeys(self):
        from PySide6.QtWidgets import QKeySequenceEdit
        self.app.open_settings()
        editors = self.app.settings_dialog.findChildren(QKeySequenceEdit)
        self.assertEqual(len(editors), 2)


if __name__ == '__main__':
    unittest.main()
