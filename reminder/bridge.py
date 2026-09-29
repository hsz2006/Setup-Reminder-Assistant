import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .bili_usage import BiliUsage
from .focus import normalize_links

PORT = 49573


class Bridge:
    def __init__(self, store, focus, events):
        self.store, self.focus, self.events = store, focus, events
        self.token = store.get('bridge_token')
        if not self.token:
            self.token = secrets.token_urlsafe(32)
            store.set('bridge_token', self.token)
        self.clients = {}
        self.lock = threading.Lock()
        self.changed = threading.Event()
        self.desktop = {}
        self.usage = BiliUsage(store)
        self.usage_lock = threading.Lock()

    def usage_paused(self, now=None):
        return bool(self.focus.blocking(now) or self.store.get('meeting_mode', False) or self.desktop.get('locked'))

    def usage_due(self, now, locked=False):
        self.desktop['locked'] = locked
        with self.usage_lock:
            return self.usage.poll(now, self.usage_paused())

    def usage_delivered(self):
        with self.usage_lock:
            self.usage.delivered()

    def usage_action(self, now, locked=False):
        self.desktop['locked'] = locked
        with self.usage_lock:
            previous = self.store.get('bili_lock', {})
            if previous and now >= previous['end'] and self.store.claim('bili_unlock:' + previous['id']):
                self.usage.advance(now, paused=True)
            due = self.usage.poll(now, self.usage_paused(now))
            if self.usage.seconds >= self.usage.LOCK_AFTER:
                self.focus.lock_bili(now)
                self.usage.advance(now, paused=True)
                self.changed.set()
                return 'bili_lock'
            return 'remind' if due else None

    def append_allow(self, videos):
        if not isinstance(videos, list):
            raise ValueError('推送内容无效。')
        if self.focus.blocking():
            raise ValueError('网站限制进行中，结束前不能修改允许列表。')
        existing = normalize_links(self.store.get('allow_draft', ''))
        merged, added = list(existing), 0
        for video in normalize_links('\n'.join(str(item) for item in videos)):
            if video not in merged:
                merged.append(video)
                added += 1
        if len(merged) > 500:
            raise ValueError('一次最多允许 500 个视频。')
        self.store.set('allow_draft', '\n'.join(merged))
        return {'added': added, 'total': len(merged)}

    def status(self):
        with self.lock:
            return {k: dict(v) for k, v in self.clients.items()}

    def ready(self):
        state = self.status()
        return all(time.time() - state.get(k, {}).get('seen', 0) < 45 and
                   not state.get(k, {}).get('error') for k in ('Chrome', 'Edge'))

    def start(self, port=PORT):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, code, data):
                body = json.dumps(data).encode()
                self.send_response(code)
                origin = self.headers.get('Origin', '')
                if origin.startswith('chrome-extension://'):
                    self.send_header('Access-Control-Allow-Origin', origin)
                    self.send_header('Vary', 'Origin')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_OPTIONS(self):
                self.send_response(204)
                origin = self.headers.get('Origin', '')
                if origin.startswith('chrome-extension://'):
                    self.send_header('Access-Control-Allow-Origin', origin)
                    self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
                    self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                self.end_headers()

            def do_POST(self):
                actual_port = self.server.server_address[1]
                if self.headers.get('Host') not in (f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'):
                    return self.send(403, {'error': 'invalid host'})
                if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + owner.token):
                    return self.send(401, {'error': 'pairing required'})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 <= length <= 8192:
                        raise ValueError()
                    data = json.loads(self.rfile.read(length) or '{}')
                    if not isinstance(data, dict):
                        raise ValueError()
                except (ValueError, json.JSONDecodeError):
                    return self.send(400, {'error': 'invalid body'})
                if self.path == '/status':
                    current = owner.focus.current()
                    clients = owner.status()
                    stamp = time.time()
                    for client in clients.values():
                        client['age_seconds'] = round(stamp - client['seen'], 1)
                        client['online'] = stamp - client['seen'] < 45
                        client['synced'] = bool(current) and client['id'] == current['id'] and not client['error']
                    with owner.usage_lock:
                        activity = {key: {'age_seconds': round(stamp - value['seen'], 1),
                                         'focused': value['focused'], 'bilibili': value['bilibili']}
                                    for key, value in owner.usage.clients.items()}
                        usage = {'seconds': round(owner.usage.seconds, 1), 'activity': activity,
                                 'lock_end': owner.focus.bili_lock().get('end')}
                    return self.send(200, {'ready': owner.ready(), 'clients': clients, 'bili_usage': usage,
                                           'focus_active': bool(current), 'focus_end': current.get('end'),
                                           'desktop': dict(owner.desktop)})
                if self.path == '/show':
                    owner.events.put(('show', None))
                    return self.send(200, {'ok': True})
                if self.path == '/allow' and data.get('browser') in ('Chrome', 'Edge'):
                    try:
                        return self.send(200, {'ok': True, **owner.append_allow(data.get('videos'))})
                    except ValueError as error:
                        return self.send(400, {'error': str(error)})
                if self.path == '/activity' and data.get('browser') in ('Chrome', 'Edge'):
                    with owner.usage_lock:
                        owner.usage.report(data['browser'], data, time.time(), owner.usage_paused())
                    return self.send(200, {'ok': True})
                if self.path != '/sync' or data.get('browser') not in ('Chrome', 'Edge'):
                    return self.send(404, {'error': 'not found'})
                with owner.lock:
                    owner.clients[data['browser']] = {'seen': time.time(), 'id': data.get('id', ''),
                                                      'error': str(data.get('error', ''))[:200],
                                                      'version': str(data.get('version', 'unknown'))[:20],
                                                      'activity_error': str(data.get('activity_error', ''))[:200]}
                current = owner.focus.blocking()
                if data.get('wait') and data.get('id', '') == current.get('id', ''):
                    owner.changed.wait(20)
                self.send(200, {'focus': owner.focus.blocking()})

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
