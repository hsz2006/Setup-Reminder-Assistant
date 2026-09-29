importScripts('policy.js');
importScripts('activity.js');
const endpoint = 'http://127.0.0.1:49573/sync';
const browser = navigator.userAgent.includes('Edg/') ? 'Edge' : 'Chrome';
let running = false;
let lastApplied = null;
let errorMessage = '';
let activityRunning = false;
let activityAgain = false;
let activityError = '';

async function reportActivity() {
  if (activityRunning) { activityAgain = true; return; }
  activityRunning = true;
  try {
    const {token} = await chrome.storage.local.get('token');
    if (!token) return;
    const windows = await chrome.windows.getAll({populate: true});
    const response = await fetch('http://127.0.0.1:49573/activity', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
      body: JSON.stringify({browser, ...BiliActivity.classify(windows)}),
      signal: AbortSignal.timeout(3000)
    });
    if (!response.ok) throw new Error('计时上报失败 HTTP ' + response.status);
    activityError = '';
    await chrome.storage.local.set({activityStatus: '计时上报正常', activitySeen: Date.now()});
  } catch (error) {
    activityError = String(error.message || error);
    await chrome.storage.local.set({activityStatus: activityError});
  }
  finally {
    activityRunning = false;
    if (activityAgain) { activityAgain = false; void reportActivity(); }
  }
}

chrome.windows.onFocusChanged.addListener(() => void reportActivity());
chrome.windows.onRemoved.addListener(() => void reportActivity());
chrome.tabs.onActivated.addListener(() => void reportActivity());
chrome.tabs.onRemoved.addListener(() => void reportActivity());
chrome.tabs.onUpdated.addListener(() => void reportActivity());
setInterval(reportActivity, 5000);
void reportActivity();

async function apply(focus) {
  const valid = FocusPolicy.active(focus) ? focus : {};
  const key = JSON.stringify(valid);
  if (key === lastApplied) return;
  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: existing.map(rule => rule.id),
    addRules: FocusPolicy.rules(valid, chrome.runtime.getURL('blocked.html'))
  });
  await chrome.storage.local.set({focus: valid});
  if (valid.end) await chrome.alarms.create('focus-end', {when: valid.end * 1000});
  else await chrome.alarms.clear('focus-end');
  const tabs = await chrome.tabs.query({url: ['*://*.bilibili.com/*', '*://bilibili.com/*', '*://b23.tv/*']});
  for (const tab of tabs) {
    if (valid.end && !FocusPolicy.allowed(tab.url, valid)) {
      await chrome.tabs.update(tab.id, {url: chrome.runtime.getURL('blocked.html')});
    } else {
      try {
        await chrome.tabs.sendMessage(tab.id, {type: 'focus', focus: valid});
      } catch {
        // Covers Bilibili tabs that were open before installing the extension.
        await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['content.js']}).catch(() => {});
      }
    }
  }
  lastApplied = key;
}

async function sync(wait = true) {
  if (running) return;
  running = true;
  try {
    const stored = await chrome.storage.local.get(['token', 'focus']);
    await apply(stored.focus || {});
    if (!stored.token) throw new Error('请先粘贴桌面助手中的配对码。');
    const focus = FocusPolicy.active(stored.focus) ? stored.focus : {};
    const response = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + stored.token},
      body: JSON.stringify({browser, id: focus.id || '', error: errorMessage, wait,
        version: chrome.runtime.getManifest().version, activity_error: activityError}),
      signal: AbortSignal.timeout(25000)
    });
    if (!response.ok) throw new Error(response.status === 401 ? '配对码不正确。' : '连接失败：' + response.status);
    const data = await response.json();
    // A lost/replaced desktop database must not end an already active local session.
    const remote = data.focus || {};
    const next = FocusPolicy.active(focus) && focus.end >= (remote.end || 0) ? focus : remote;
    await apply(next);
    errorMessage = '';
    await chrome.storage.local.set({connection: '已连接 ' + browser, seen: Date.now()});
  } catch (error) {
    errorMessage = String(error.message || error);
    await chrome.storage.local.set({connection: errorMessage});
    // The local deadline and persisted DNR rules continue without the desktop process.
    const stored = await chrome.storage.local.get('focus');
    if (!FocusPolicy.active(stored.focus)) await apply({}).catch(() => {});
  } finally {
    running = false;
  }
}

async function pushAllow(videos) {
  const {token} = await chrome.storage.local.get('token');
  if (!token) throw new Error('请先保存配对码。');
  const response = await fetch('http://127.0.0.1:49573/allow', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
    body: JSON.stringify({browser, videos}),
    signal: AbortSignal.timeout(5000)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || '连接失败：' + response.status);
  return data;
}

async function loop() {
  await sync(true);
  setTimeout(loop, 1200);
}
chrome.alarms.onAlarm.addListener(async alarm => {
  void reportActivity();
  if (alarm.name === 'focus-end') {
    const stored = await chrome.storage.local.get('focus');
    if (!FocusPolicy.active(stored.focus)) await apply({});
  }
  await sync(false);
});
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('heartbeat', {periodInMinutes: 0.5});
  chrome.runtime.openOptionsPage();
});
chrome.runtime.onStartup.addListener(() => sync(false));
chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'sync') {
    sync(false).then(() => sendResponse({ok: true}));
    return true;
  }
  if (message.type === 'allow') {
    pushAllow(message.videos).then(
      data => sendResponse({ok: true, ...data}),
      error => sendResponse({ok: false, error: String(error.message || error)}));
    return true;
  }
});
chrome.tabs.onUpdated.addListener(async (tabId, change, tab) => {
  if (!change.url) return;
  let host;
  try { host = new URL(change.url).hostname; } catch { return; }
  if (!(host === 'b23.tv' || host === 'bilibili.com' || host.endsWith('.bilibili.com'))) return;
  const {focus} = await chrome.storage.local.get('focus');
  if (FocusPolicy.active(focus) && !FocusPolicy.allowed(change.url, focus)) {
    await chrome.tabs.update(tabId, {url: chrome.runtime.getURL('blocked.html')});
  }
});
chrome.alarms.create('heartbeat', {periodInMinutes: 0.5});
loop();
