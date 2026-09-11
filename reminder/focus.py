import re
import time
import uuid
from urllib.parse import urlparse


def normalize_links(text):
    """Expand a course collection explicitly to video IDs; never allow entire hosts."""
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r'BV[A-Za-z0-9]{10}', line):
            value = line
        else:
            parsed = urlparse(line)
            if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('www.bilibili.com', 'bilibili.com', 'm.bilibili.com'):
                raise ValueError('仅接受 B 站完整视频地址或 BV 号；课程合集请导入其中的视频。')
            match = re.fullmatch(r'/video/(BV[A-Za-z0-9]{10})/?', parsed.path)
            if not match:
                raise ValueError('请使用 /video/BV… 地址。短链接或合集页请先在扩展中导入。')
            value = match.group(1)
        if value not in result:
            result.append(value)
    if len(result) > 500:
        raise ValueError('一次最多允许 500 个视频。')
    return result


class Focus:
    def __init__(self, store):
        self.store = store

    def current(self, now=None):
        now = time.time() if now is None else now
        state = self.store.get('focus', {})
        return state if state.get('end', 0) > now else {}

    def start(self, minutes, links, now=None):
        now = time.time() if now is None else now
        if self.current(now):
            raise ValueError('专注尚未结束，不能修改或重新开始。')
        if not isinstance(minutes, int) or not 1 <= minutes <= 1440:
            raise ValueError('时长须为 1—1440 分钟的整数。')
        allow = normalize_links(links)
        state = {'id': uuid.uuid4().hex, 'end': now + minutes * 60, 'allow': allow}
        # Serialize the start with other processes; an active session cannot be overwritten.
        with self.store.connect() as db:
            import json
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM state WHERE key='focus'").fetchone()
            if row and json.loads(row[0]).get('end', 0) > now:
                raise ValueError('专注尚未结束。')
            db.execute('INSERT OR REPLACE INTO state VALUES(?,?)', ('focus', json.dumps(state)))
        return state
