"""Merge foreground browser observations; never count stale/offline time."""
import time
from .focus import normalize_links

WARNING = '检测到你在 B 站的停留时间已经超过 20 分钟。'


class BiliUsage:
    INTERVAL = 20 * 60
    LOCK_AFTER = 30 * 60
    AWAY_RESET = 5 * 60
    LEASE = 12

    def __init__(self, store, now=None):
        self.store = store
        self.last = time.time() if now is None else now
        saved = store.get('bili_usage', {})
        self.last_bili = saved.get('last_bili', self.last)
        self.seconds = saved.get('seconds', 0) if 0 <= self.last - self.last_bili < self.AWAY_RESET else 0
        self.clients = {}
        self.pending = False
        self.reminded = bool(saved.get('reminded', False)) if self.seconds else False

    def advance(self, now, paused=False):
        try:
            allow = set(normalize_links(self.store.get('allow_draft', '')))
        except ValueError:
            allow = set()
        # A sleeping computer or a delayed process must not fill in unobserved time.
        gap = now - self.last
        if paused:
            self.seconds = 0
            self.reminded = False
            self.pending = False
            self.last_bili = now
        elif 0 <= gap <= self.LEASE:
            sites = [c for c in self.clients.values() if c['focused'] and c['bilibili']]
            end = max((min(now, c['seen'] + self.LEASE) for c in sites), default=self.last)
            if end > self.last:
                if self.last - self.last_bili >= self.AWAY_RESET:
                    self.seconds = 0
                    self.reminded = False
                    self.pending = False
                self.last_bili = end
                counted_end = max((min(now, c['seen'] + self.LEASE) for c in sites
                                   if c['video'] not in allow), default=self.last)
                self.seconds += max(0, counted_end - self.last)
                self.pending = self.seconds >= self.INTERVAL and not self.reminded
        if now - self.last_bili >= self.AWAY_RESET:
            self.seconds = 0
            self.reminded = False
            self.pending = False
        self.last = now
        self.persist()

    def persist(self):
        value = {'seconds': self.seconds, 'last_bili': self.last_bili, 'reminded': self.reminded}
        if value != self.store.get('bili_usage', {}):
            self.store.set('bili_usage', value)

    def report(self, browser, data, now, paused=False):
        self.advance(now, paused)
        if data.get('focused') is True:
            for client in self.clients.values():
                client['focused'] = False
        self.clients[browser] = {
            'focused': data.get('focused') is True,
            'bilibili': data.get('bilibili') is True,
            'video': str(data.get('video', ''))[:12], 'seen': now,
        }

    def poll(self, now, paused=False):
        self.advance(now, paused)
        return self.pending

    def delivered(self):
        self.pending = False
        self.reminded = True
        self.persist()
