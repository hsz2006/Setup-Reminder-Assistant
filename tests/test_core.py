import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from reminder.storage import Store
from reminder.rules import load_config, in_class, ordinary_allowed, scheduled, next_action, school_day
from reminder.focus import Focus, normalize_links
from reminder.ai import AI


class CalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()

    def dt(self, value):
        return datetime.fromisoformat(value)

    def test_tuesday_overlapping_course(self):
        self.assertTrue(in_class(self.dt('2026-09-15T14:30'), self.cfg))
        self.assertFalse(in_class(self.dt('2026-09-15T16:00'), self.cfg))
        self.assertIn('图论', scheduled(self.dt('2026-09-15T16:00'), self.cfg))

    def test_course_week_expiry(self):
        self.assertFalse(ordinary_allowed(self.dt('2026-11-10T09:00'), self.cfg))
        self.assertTrue(ordinary_allowed(self.dt('2026-11-17T09:00'), self.cfg))

    def test_thursday_laboratory_weeks(self):
        self.assertFalse(in_class(self.dt('2026-09-17T14:30'), self.cfg))
        self.assertTrue(in_class(self.dt('2026-10-08T14:30'), self.cfg))
        self.assertFalse(in_class(self.dt('2026-12-10T14:30'), self.cfg))

    def test_four_experiments_and_other_mondays(self):
        for day in ['2026-10-12', '2026-10-19', '2026-11-09', '2026-11-23']:
            self.assertTrue(in_class(self.dt(day + 'T20:00'), self.cfg))
            self.assertFalse(in_class(self.dt(day + 'T21:55'), self.cfg))
        self.assertFalse(in_class(self.dt('2026-10-26T20:00'), self.cfg))

    def test_holiday_has_no_class_or_wednesday_1600(self):
        self.assertFalse(in_class(self.dt('2026-10-07T14:30'), self.cfg))
        self.assertIsNotNone(scheduled(self.dt('2026-10-07T14:30'), self.cfg))
        self.assertIsNone(scheduled(self.dt('2026-10-07T16:00'), self.cfg))
        self.assertIn('科研', scheduled(self.dt('2026-10-07T19:30'), self.cfg))

    def test_graph_holiday_and_term_expiry(self):
        self.assertIsNone(scheduled(self.dt('2026-10-06T16:00'), self.cfg))
        self.assertIsNone(scheduled(self.dt('2026-12-15T16:00'), self.cfg))

    def test_makeup_tuesday(self):
        self.assertTrue(in_class(self.dt('2026-10-10T09:00'), self.cfg))
        self.assertTrue(in_class(self.dt('2026-10-10T14:30'), self.cfg))
        self.assertIsNone(scheduled(self.dt('2026-10-10T16:00'), self.cfg))
        self.assertIsNotNone(scheduled(self.dt('2026-10-10T19:00'), self.cfg))

    def test_sunday_is_start_of_calendar_week(self):
        week, dow, holiday = school_day(self.dt('2026-09-20T10:00').date(), self.cfg)
        self.assertEqual((week, dow, holiday), (4, 4, False))
        self.assertFalse(in_class(self.dt('2026-09-20T10:00'), self.cfg))

    def test_spring_stops_ordinary_but_keeps_research(self):
        self.assertIsNotNone(scheduled(self.dt('2027-02-20T09:00'), self.cfg))
        self.assertIsNone(scheduled(self.dt('2027-02-21T09:00'), self.cfg))
        self.assertIn('科研', scheduled(self.dt('2027-02-21T14:30'), self.cfg))
        self.assertIn('科研', scheduled(self.dt('2027-02-24T19:30'), self.cfg))

    def test_window_bounds(self):
        self.assertFalse(ordinary_allowed(self.dt('2026-09-12T08:29'), self.cfg))
        self.assertTrue(ordinary_allowed(self.dt('2026-09-12T08:30'), self.cfg))
        self.assertTrue(ordinary_allowed(self.dt('2026-09-12T22:30'), self.cfg))
        self.assertFalse(ordinary_allowed(self.dt('2026-09-12T22:31'), self.cfg))

    def test_default_stable_and_switchable(self):
        dt = self.dt('2026-09-12T09:00')
        self.assertEqual(next_action(dt, self.cfg, []), next_action(dt, self.cfg, []))
        self.assertTrue(next_action(dt, self.cfg, [], 1)[0])
        tasks = [{'id': 1, 'text': 'a'}, {'id': 2, 'text': 'b'}]
        self.assertEqual(next_action(dt, self.cfg, tasks, 1), ('b', 2))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path / 'test.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def test_tasks_survive_multiple_days(self):
        self.store.add_tasks(['读三页'], '2026-09-10')
        self.store.add_tasks(['明天的事'], '2026-09-15')
        tasks = self.store.tasks('2026-09-14')
        self.assertEqual(len(tasks), 1)
        self.store.update_task(tasks[0]['id'], status='done')
        self.assertEqual(self.store.tasks('2026-09-14'), [])

    def test_reopen_shared_store_and_chat(self):
        self.store.add_tasks(['打开书'])
        self.store.chat('user', '昨天的讨论')
        other = Store(self.path / 'test.sqlite3')
        self.assertEqual(other.tasks()[0]['text'], '打开书')
        self.assertEqual(other.chat()[0]['content'], '昨天的讨论')
        other.clear_chat()
        self.assertEqual(self.store.chat(), [])

    def test_focus_persists_and_cannot_be_replaced(self):
        focus = Focus(self.store)
        state = focus.start(25, 'https://www.bilibili.com/video/BV1234567890/?p=2', now=1000)
        self.assertEqual(state['end'], 2500)
        self.assertEqual(Focus(Store(self.path / 'test.sqlite3')).current(2000)['allow'], ['BV1234567890'])
        with self.assertRaises(ValueError):
            focus.start(1, '', now=2000)
        self.assertEqual(focus.current(2500), {})
        self.assertTrue(focus.start(1, '', now=2500))

    def test_links_cannot_allow_entire_site(self):
        for link in ['https://www.bilibili.com/', 'https://www.bilibili.com.evil/video/BV1234567890',
                     'https://www.bilibili.com/video/BV1234567890/extra', 'https://b23.tv/abcd']:
            with self.assertRaises(ValueError):
                normalize_links(link)
        self.assertEqual(normalize_links('BV1234567890\nBV1234567890'), ['BV1234567890'])

    def test_event_claim_once_across_restarts(self):
        self.assertTrue(self.store.claim('one'))
        self.assertFalse(Store(self.path / 'test.sqlite3').claim('one'))

    def test_ai_disabled_makes_no_request(self):
        config = self.path / 'disabled-ai.json'
        config.write_text(json.dumps({'enabled': False}), encoding='utf-8')
        with patch('urllib.request.urlopen') as request:
            with self.assertRaises(ValueError):
                AI(self.store, config).ask('写一个任务')
            request.assert_not_called()

    def test_ai_draft_requires_explicit_save(self):
        config = self.path / 'ai.json'
        config.write_text(json.dumps({'enabled': True, 'base_url': 'https://example.invalid/v1', 'model': 'future-model', 'api_key': 'test-only'}))
        import io
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': '{"tasks":["打开书"]}'}}]}).encode())
        with patch('urllib.request.urlopen', return_value=response) as request:
            tasks = AI(self.store, config).ask('看书', draft=True)
            self.assertEqual(tasks, ['打开书'])
            self.assertEqual(self.store.tasks(), [])
            sent = json.loads(request.call_args.args[0].data)
            self.assertEqual(sent['model'], 'future-model')
        self.store.add_tasks(tasks)
        self.assertEqual(len(self.store.tasks()), 1)


if __name__ == '__main__':
    unittest.main()
