import json
import queue
import tempfile
import unittest
import urllib.error
import urllib.request
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


if __name__ == '__main__':
    unittest.main()
