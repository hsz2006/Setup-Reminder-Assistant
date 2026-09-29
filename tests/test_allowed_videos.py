import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from reminder.storage import Store
from reminder.focus import Focus
from reminder.allowed_videos import AllowedVideos, fetch_title, open_edge


class AllowedVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite3')
        self.focus = Focus(self.store)
        self.session = self.focus.start(40, 'BV1234567890')

    def tearDown(self):
        self.temp.cleanup()

    def test_titles_cache_failure_and_actual_allowlist(self):
        self.store.set('allow_draft', 'BV0987654321')
        opener, notice = Mock(), Mock()
        page = AllowedVideos(self.store, self.focus, self.session, notice, loader=lambda bv: '', opener=opener)
        self.assertEqual(list(page.labels), ['BV1234567890'])
        page.title_ready('BV1234567890', '')
        self.assertIn('标题暂不可用', page.labels['BV1234567890'].text())
        page.open('BV1234567890')
        opener.assert_called_once_with('BV1234567890')
        page.title_ready('BV1234567890', '<课程标题>')
        self.assertEqual(self.store.get('video_titles')['BV1234567890'], '<课程标题>')
        self.store.set('focus', {})
        page.open('BV1234567890')
        self.assertEqual(opener.call_count, 1)
        notice.assert_called_once()
        page.stop()
        page.deleteLater()
        self.qt.processEvents()

    def test_title_parser_and_edge_scheme(self):
        response = Mock()
        response.read.return_value = json.dumps({'code': 0, 'data': {'title': '课程标题'}}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('reminder.allowed_videos.urllib.request.urlopen', return_value=response):
            self.assertEqual(fetch_title('BV1234567890'), '课程标题')
            response.read.return_value = b'{"code":-404}'
            with self.assertRaises(ValueError):
                fetch_title('BV1234567890')
        with patch('reminder.allowed_videos.os.startfile') as launch:
            open_edge('BV1234567890')
            launch.assert_called_once_with('microsoft-edge:https://www.bilibili.com/video/BV1234567890/')

    def test_empty_list_and_cached_titles_need_no_requests(self):
        session = dict(self.session, allow=[])
        page = AllowedVideos(self.store, self.focus, session, Mock(), loader=Mock())
        self.assertEqual(page.missing, [])
        page.load_titles()
        page.loader.assert_not_called()
        page.stop()
        page.deleteLater()
        self.qt.processEvents()
