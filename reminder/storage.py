import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else ROOT / 'data' / 'reminder.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', due TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, text TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chat(id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(key TEXT PRIMARY KEY, created TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO state VALUES(?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def claim(self, key):
        with self.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO events VALUES(?,?)', (key, datetime.now().isoformat()))
            return cur.rowcount == 1

    def tasks(self, day=None, all_pending=False):
        with self.connect() as db:
            query = "SELECT * FROM tasks WHERE status='pending'"
            args = []
            if day and not all_pending:
                query += " AND (due='' OR due<=?)"
                args.append(day)
            return [dict(r) for r in db.execute(query + ' ORDER BY id', args)]

    def add_tasks(self, texts, due=''):
        if due:
            datetime.strptime(due, '%Y-%m-%d')
        clean = [str(t).strip() for t in texts if str(t).strip()]
        if not clean:
            raise ValueError('请至少填写一个任务。')
        with self.connect() as db:
            db.executemany('INSERT INTO tasks(text,due,created) VALUES(?,?,?)',
                           [(t, due, datetime.now().isoformat()) for t in clean])

    def update_task(self, task_id, text=None, status=None):
        with self.connect() as db:
            if text is not None:
                if not text.strip():
                    raise ValueError('任务不能为空。')
                db.execute('UPDATE tasks SET text=? WHERE id=?', (text.strip(), task_id))
            if status is not None:
                if status not in ('pending', 'done', 'shelved'):
                    raise ValueError('无效任务状态。')
                db.execute('UPDATE tasks SET status=? WHERE id=?', (status, task_id))

    def review(self, text):
        if text.strip():
            with self.connect() as db:
                db.execute('INSERT INTO reviews(text,created) VALUES(?,?)', (text.strip(), datetime.now().isoformat()))

    def reviews(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT text,created FROM reviews ORDER BY id DESC LIMIT 7')]

    def chat(self, role=None, content=None):
        with self.connect() as db:
            if role:
                db.execute('INSERT INTO chat(role,content) VALUES(?,?)', (role, content))
            return [dict(r) for r in db.execute('SELECT role,content FROM (SELECT * FROM chat ORDER BY id DESC LIMIT 24) ORDER BY id')]

    def clear_chat(self):
        with self.connect() as db:
            db.execute('DELETE FROM chat')
