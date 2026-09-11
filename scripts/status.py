"""Read actual extension heartbeats without impersonating a browser."""
import json
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reminder.storage import Store
from reminder.bridge import PORT

token = Store().get('bridge_token', '')
request = urllib.request.Request(f'http://127.0.0.1:{PORT}/status', b'{}',
                                {'Authorization': 'Bearer ' + token})
try:
    with urllib.request.urlopen(request, timeout=3) as response:
        print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
except urllib.error.HTTPError as error:
    print('状态接口不可用，HTTP ' + str(error.code) + '；请重启桌面助手使新代码生效。')
    sys.exit(1)
except urllib.error.URLError:
    print('桌面助手未运行或本机连接不可用。')
    sys.exit(1)
