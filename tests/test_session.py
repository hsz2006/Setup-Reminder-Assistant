import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from reminder.storage import Store
from reminder.focus import Focus
from reminder.rules import load_config, day_agenda
from reminder.session import Session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite3')
        self.now = datetime(2026, 9, 16, 18, 59, 50)
        self.focus = Focus(self.store)
        self.session = Session(self.store, self.focus, load_config(), self.now)

    def tearDown(self):
        self.temp.cleanup()

    def test_meeting_persists_until_manual_restore(self):
        self.session.set_meeting(True, self.now)
        again = Session(self.store, self.focus, load_config(), self.now + timedelta(days=1))
        self.assertTrue(again.meeting)
        again.set_meeting(False, self.now + timedelta(days=1))
        self.assertFalse(self.session.meeting)

    def test_no_scheduled_catchup_on_restore(self):
        self.session.set_meeting(True, self.now)
        due = self.now.replace(hour=19, minute=0, second=0)
        self.assertIsNone(self.session.poll(due))
        self.session.set_meeting(False, due + timedelta(seconds=4))
        self.assertIsNone(self.session.poll(due + timedelta(seconds=5)))

    def test_expired_rest_and_focus_consumed_without_alert(self):
        self.focus.start(1, '', now=self.now.timestamp())
        self.store.set('rest_end', self.now.timestamp() + 30)
        self.session.set_meeting(True, self.now)
        expired = self.now + timedelta(minutes=2)
        self.assertIsNone(self.session.poll(expired, locked=True))
        self.assertEqual(self.store.get('rest_end'), 0)
        self.assertFalse(self.focus.current(expired.timestamp()))
        self.session.set_meeting(False, expired)
        self.assertIsNone(self.session.poll(expired + timedelta(seconds=1)))

    def test_focus_not_cancelled_by_meeting(self):
        state = self.focus.start(25, '', now=self.now.timestamp())
        self.session.set_meeting(True, self.now)
        self.session.set_meeting(False, self.now + timedelta(minutes=2))
        self.assertEqual(self.focus.current(self.now.timestamp() + 120), state)

    def test_agenda_uses_actual_courses_and_fixed_times(self):
        items = day_agenda(datetime(2026, 9, 15).date(), load_config())
        names = [item['name'] for item in items]
        self.assertIn('模拟与数字电路 A', names)
        self.assertIn('图论自学', names)
        self.assertNotIn('图论（周二课后自学）', names)
        holiday = day_agenda(datetime(2026, 10, 7).date(), load_config())
        self.assertEqual([item['name'] for item in holiday], ['科研'])
