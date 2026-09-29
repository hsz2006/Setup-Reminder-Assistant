import unittest
from reminder.bili_usage import BiliUsage


class MemoryStore:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.usage = BiliUsage(self.store, now=0)

    def report(self, stamp, browser='Chrome', focused=True, bili=True, video='', paused=False):
        self.usage.report(browser, {'focused': focused, 'bilibili': bili, 'video': video}, stamp, paused)

    def watch(self, start, stop, **kwargs):
        for stamp in range(start, stop + 1, 5):
            self.report(stamp, **kwargs)

    def test_reminder_preserves_total_until_focus_threshold(self):
        self.watch(0, 1195)
        self.assertFalse(self.usage.pending)
        self.report(1200)
        self.assertTrue(self.usage.pending)
        self.usage.delivered()
        self.watch(1205, 1795)
        self.assertFalse(self.usage.pending)
        self.report(1800)
        self.assertFalse(self.usage.pending)
        self.assertEqual(self.usage.seconds, self.usage.LOCK_AFTER)

    def test_two_browsers_merge_without_double_counting(self):
        self.watch(0, 600)
        for stamp in range(605, 1201, 5):
            self.report(stamp, browser='Edge')
            self.report(stamp, browser='Chrome', focused=False)
        self.assertTrue(self.usage.pending)
        self.assertEqual(self.usage.seconds, 1200)

    def test_allowlist_and_background_do_not_count(self):
        self.store.set('allow_draft', 'BV1234567890')
        self.watch(0, 1500, video='BV1234567890')
        self.assertEqual(self.usage.seconds, 0)
        self.watch(1505, 3000, focused=False)
        self.assertEqual(self.usage.seconds, 0)
        self.assertFalse(self.usage.pending)

    def test_short_break_keeps_time_five_minutes_resets(self):
        self.watch(0, 600)
        self.report(600, bili=False)
        for stamp in range(605, 900, 5):
            self.report(stamp, bili=False)
        self.assertEqual(self.usage.seconds, 600)
        self.report(900, bili=False)
        self.assertEqual(self.usage.seconds, 0)
        self.watch(905, 1205)
        self.assertEqual(self.usage.seconds, 300)

    def test_paused_clears_due_and_restarts_from_zero(self):
        self.watch(0, 1200)
        self.assertTrue(self.usage.pending)
        self.report(1201, paused=True)
        self.assertEqual(self.usage.seconds, 0)
        self.assertFalse(self.usage.pending)
        self.watch(1205, 1500, paused=True)
        self.watch(1505, 1805)
        self.assertLessEqual(self.usage.seconds, 305)
        self.assertFalse(self.usage.pending)

    def test_disconnection_and_sleep_do_not_fill_unobserved_time(self):
        self.watch(0, 60)
        for stamp in range(61, 121):
            self.usage.poll(stamp)
        self.assertEqual(self.usage.seconds, 72)
        self.usage.poll(2000)
        self.assertEqual(self.usage.seconds, 0)
        self.assertFalse(self.usage.pending)

    def test_restart_preserves_short_break_but_not_old_session(self):
        self.watch(0, 600)
        self.assertEqual(BiliUsage(self.store, now=650).seconds, 600)
        self.assertEqual(BiliUsage(self.store, now=901).seconds, 0)

    def test_restart_after_reminder_keeps_full_total_and_delivery_state(self):
        self.watch(0, 1800)
        self.usage.delivered()
        resumed = BiliUsage(self.store, now=1805)
        self.assertEqual(resumed.seconds, 1800)
        self.assertTrue(resumed.reminded)
        self.assertFalse(resumed.poll(1806))
