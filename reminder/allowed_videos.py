"""Read-only links for the active focus session, with asynchronous titles."""
import json
import os
import re
import threading
import urllib.request
from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea


def video_url(bv):
    if not re.fullmatch(r'BV[A-Za-z0-9]{10}', bv):
        raise ValueError('无效的视频 BV 号。')
    return 'https://www.bilibili.com/video/' + bv + '/'


def fetch_title(bv):
    video_url(bv)
    request = urllib.request.Request(
        'https://api.bilibili.com/x/web-interface/view?bvid=' + bv,
        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bilibili.com/'})
    with urllib.request.urlopen(request, timeout=6) as response:
        data = json.loads(response.read(1024 * 1024))
    title = data.get('data', {}).get('title') if data.get('code') == 0 else None
    if not isinstance(title, str) or not title.strip():
        raise ValueError('未能获取视频标题。')
    return title.strip()[:500]


def open_edge(bv):
    os.startfile('microsoft-edge:' + video_url(bv))


class TitleSignals(QObject):
    result = Signal(str, str)


class AllowedVideos(QWidget):
    def __init__(self, store, focus, session, notice, parent=None, loader=fetch_title, opener=open_edge):
        super().__init__(parent)
        self.store, self.focus, self.session = store, focus, session
        self.notice, self.loader, self.opener = notice, loader, opener
        self.stopped = threading.Event()
        self.signals = TitleSignals(self)
        self.signals.result.connect(self.title_ready)
        self.labels = {}
        layout = QVBoxLayout(self)
        hint = QLabel('当前限制允许的视频，点击后使用 Edge 打开。\n个人专注或 B 站锁定期间不能增删；分 P 可在视频页面选择。')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(260)
        body = QWidget()
        rows = QVBoxLayout(body)
        cache = store.get('video_titles', {})
        self.missing = []
        for bv in session['allow']:
            row = QHBoxLayout()
            texts = QVBoxLayout()
            title = QLabel(cache.get(bv, '正在获取标题…'))
            title.setTextFormat(Qt.TextFormat.PlainText)
            title.setWordWrap(True)
            title.setObjectName('videoTitle')
            title.setMinimumWidth(240)
            texts.addWidget(title)
            identifier = QLabel(bv)
            identifier.setObjectName('muted')
            texts.addWidget(identifier)
            row.addLayout(texts, 1)
            launch = QPushButton('Edge 打开')
            launch.clicked.connect(lambda checked=False, value=bv: self.open(value))
            row.addWidget(launch)
            rows.addLayout(row)
            self.labels[bv] = title
            if bv not in cache:
                self.missing.append(bv)
        if not session['allow']:
            rows.addWidget(QLabel('本次专注没有允许播放的视频。'))
        rows.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll)
        QTimer.singleShot(0, self.load_titles)

    def stop(self):
        self.stopped.set()

    def load_titles(self):
        def work():
            for bv in self.missing:
                if self.stopped.is_set():
                    break
                try:
                    title = self.loader(bv)
                except Exception:
                    title = ''
                if self.stopped.is_set():
                    break
                try:
                    self.signals.result.emit(bv, title)
                except RuntimeError:
                    break
        if self.missing and not self.stopped.is_set():
            threading.Thread(target=work, daemon=True).start()

    def title_ready(self, bv, title):
        if self.stopped.is_set():
            return
        self.labels[bv].setText(title or '标题暂不可用，可通过 BV 号打开')
        if title:
            cache = self.store.get('video_titles', {})
            cache[bv] = title
            self.store.set('video_titles', cache)

    def open(self, bv):
        current = self.focus.blocking()
        if current.get('id') != self.session['id'] or bv not in current.get('allow', []):
            self.notice('专注状态已变化', '请关闭此页面，重新打开允许列表。')
            return
        try:
            self.opener(bv)
        except OSError:
            self.notice('无法打开 Edge', '请确认 Microsoft Edge 已安装且可以正常启动。')
