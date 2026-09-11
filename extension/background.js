importScripts('policy.js');
const endpoint = 'http://127.0.0.1:49573/sync';
const browser = navigator.userAgent.includes('Edg/') ? 'Edge' : 'Chrome';
let running = false;
let lastApplied = null;
let errorMessage = '';

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
      body: JSON.stringify({browser, id: focus.id || '', error: errorMessage, wait}),
      signal: AbortSignal.timeout(25000)
    });
    if (!response.ok) throw new Error(response.status === 401 ? '配对码不正确。' : '连接失败：' + response.status);
    const data = await response.json();
    // A lost/replaced desktop database must not end an already active local session.
    const next = FocusPolicy.active(focus) ? focus : (data.focus || {});
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

async function loop() {
  await sync(true);
  setTimeout(loop, 1200);
}
chrome.alarms.onAlarm.addListener(async alarm => {
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
