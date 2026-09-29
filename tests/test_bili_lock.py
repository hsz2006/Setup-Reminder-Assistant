import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from reminder.focus import Focus
from reminder.storage import Store


class BiliLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'lock.sqlite3')
        self.store.set('allow_draft', 'BV1234567890')
        self.focus = Focus(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_early_morning_and_daytime_both_expire_tomorrow(self):
        for hour in (0, 7, 8, 23):
            self.store.set('bili_lock', {})
            now = datetime(2026, 9, 27, hour).timestamp()
            state = self.focus.lock_bili(now)
            end = datetime(2026, 9, 28, 8).timestamp()
            self.assertEqual(state['end'], end)
            self.assertTrue(Focus(Store(self.store.path)).bili_lock(end - 1))
            self.assertFalse(self.focus.bili_lock(end))
            self.assertFalse(self.focus.current(now))

    def test_personal_focus_uses_frozen_allowlist_and_does_not_shorten_lock(self):
        now = datetime(2026, 9, 27, 12).timestamp()
        lock = self.focus.lock_bili(now)
        self.store.set('allow_draft', 'BV0987654321')
        personal = self.focus.start(25, 'BV0987654321', now)
        self.assertEqual(personal['allow'], lock['allow'])
        self.assertEqual(self.focus.blocking(now)['id'], lock['id'])
        self.assertFalse(self.focus.current(now + 1500))
        self.assertTrue(self.focus.blocking(now + 1500))
        self.store.set('meeting_mode', True)
        self.assertTrue(self.focus.bili_lock(now + 3600))
