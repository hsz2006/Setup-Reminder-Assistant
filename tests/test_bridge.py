import json
import queue
import tempfile
import unittest
import urllib.error
import urllib.request
import time
from pathlib import Path
from reminder.storage import Store
from reminder.focus import Focus
from reminder.bridge import Bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite3')
        self.bridge = Bridge(self.store, Focus(self.store), queue.Queue())
        self.bridge.start(port=0)
        self.url = 'http://127.0.0.1:' + str(self.bridge.server.server_address[1])

    def tearDown(self):
        self.bridge.server.shutdown()
        self.bridge.server.server_close()
        self.temp.cleanup()

    def post(self, route, data, token=None):
        request = urllib.request.Request(self.url + route, json.dumps(data).encode(),
                      {'Authorization': 'Bearer ' + (self.bridge.token if token is None else token)})
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response)

    def test_status_does_not_create_heartbeats(self):
        state = self.post('/status', {})
        self.assertEqual(state['clients'], {})
        self.assertFalse(state['ready'])
        self.assertFalse(state['focus_active'])

    def test_two_clients_required_and_acknowledged(self):
        self.post('/sync', {'browser': 'Chrome'})
        self.assertFalse(self.post('/status', {})['ready'])
        self.post('/sync', {'browser': 'Edge'})
        self.assertTrue(self.post('/status', {})['ready'])
        focus = self.bridge.focus.start(1, '')
        received = self.post('/sync', {'browser': 'Chrome'})
        self.assertEqual(received['focus']['id'], focus['id'])
        self.assertFalse(self.post('/status', {})['clients']['Chrome']['synced'])
        self.post('/sync', {'browser': 'Chrome', 'id': focus['id']})
        self.assertTrue(self.post('/status', {})['clients']['Chrome']['synced'])

    def test_status_requires_pairing_token(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/status', {}, token='incorrect')
        self.assertEqual(caught.exception.code, 401)

    def test_activity_is_authenticated_and_independent_of_focus_sync(self):
        payload = {'browser': 'Chrome', 'focused': True, 'bilibili': True, 'video': ''}
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/activity', payload, token='incorrect')
        self.assertEqual(caught.exception.code, 401)
        self.assertTrue(self.post('/activity', payload)['ok'])
        self.assertEqual(self.bridge.status(), {})
        self.assertTrue(self.bridge.usage.clients['Chrome']['bilibili'])
        self.store.set('meeting_mode', True)
        self.bridge.usage.seconds = 100
        self.post('/activity', payload)
        self.assertEqual(self.bridge.usage.seconds, 0)

    def test_automatic_focus_without_two_online_clients_and_late_sync(self):
        now = time.time()
        self.store.set('allow_draft', 'BV1234567890')
        self.post('/sync', {'browser': 'Edge'})
        self.assertFalse(self.bridge.ready())
        self.bridge.usage.last = now
        self.bridge.usage.last_bili = now
        self.bridge.usage.seconds = 1800
        self.assertEqual(self.bridge.usage_action(now), 'bili_lock')
        current = self.bridge.focus.bili_lock(now)
        self.assertFalse(self.bridge.focus.current(now))
        self.assertGreater(current['end'], now)
        self.assertEqual(current['allow'], ['BV1234567890'])
        self.assertEqual(self.bridge.usage.seconds, 0)
        self.assertTrue(self.bridge.changed.is_set())
        self.assertEqual(self.post('/sync', {'browser': 'Chrome'})['focus'], current)
        self.assertIsNone(self.bridge.usage_action(now + 1))
        self.assertEqual(self.bridge.focus.bili_lock(now + 1)['id'], current['id'])
        self.assertIsNone(self.bridge.usage_action(now + 2401))
        self.assertEqual(self.bridge.usage.seconds, 0)

    def test_push_allowlist_merges_and_deduplicates(self):
        self.store.set('allow_draft', 'BV1234567890')
        pushed = self.post('/allow', {'browser': 'Chrome', 'videos': ['BV0987654321', 'BV1234567890']})
        self.assertEqual(pushed['added'], 1)
        self.assertEqual(pushed['total'], 2)
        self.assertEqual(self.store.get('allow_draft'), 'BV1234567890\nBV0987654321')
        again = self.post('/allow', {'browser': 'Edge', 'videos': ['BV0987654321']})
        self.assertEqual(again['added'], 0)
        self.assertEqual(again['total'], 2)

    def test_push_allowlist_rejected_during_focus_and_invalid_input(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/allow', {'browser': 'Chrome', 'videos': ['BV1234567890']}, token='incorrect')
        self.assertEqual(caught.exception.code, 401)
        self.bridge.focus.start(1, 'BV1234567890')
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/allow', {'browser': 'Chrome', 'videos': ['BV0987654321']})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.store.get('allow_draft'), None)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/allow', {'browser': 'Chrome', 'videos': 'not-a-list'})
        self.assertEqual(caught.exception.code, 400)

    def test_automatic_focus_empty_allowlist_and_paused_states(self):
        now = time.time()
        for meeting, locked in ((True, False), (False, True), (False, False)):
            self.store.set('meeting_mode', meeting)
            self.bridge.usage.last = self.bridge.usage.last_bili = now
            self.bridge.usage.seconds = 1800
            result = self.bridge.usage_action(now, locked)
            self.assertEqual(result, None if meeting or locked else 'bili_lock')
        self.assertEqual(self.bridge.focus.bili_lock(now)['allow'], [])


if __name__ == '__main__':
    unittest.main()
