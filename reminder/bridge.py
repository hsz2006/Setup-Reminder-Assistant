import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
                    return self.send(200, {'ready': owner.ready(), 'clients': clients,
                                           'focus_active': bool(current), 'focus_end': current.get('end'),
                                           'desktop': dict(owner.desktop)})
                if self.path == '/show':
                    owner.events.put(('show', None))
                    return self.send(200, {'ok': True})
                if self.path != '/sync' or data.get('browser') not in ('Chrome', 'Edge'):
                    return self.send(404, {'error': 'not found'})
                with owner.lock:
                    owner.clients[data['browser']] = {'seen': time.time(), 'id': data.get('id', ''),
                                                      'error': str(data.get('error', ''))[:200]}
                current = owner.focus.current()
                if data.get('wait') and data.get('id', '') == current.get('id', ''):
                    owner.changed.wait(20)
                self.send(200, {'focus': owner.focus.current()})

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
