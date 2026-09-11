const $ = id => document.getElementById(id);
async function status() {
  const data = await chrome.storage.local.get(['connection', 'focus']);
  $('connection').textContent = data.connection || '尚未连接';
  const active = data.focus?.end > Date.now() / 1000;
  $('save').disabled = active;
  $('token').disabled = active;
  if (active) $('connection').textContent += ' · 专注中，配对设置已锁定';
}
chrome.storage.local.get('token').then(data => {$('token').value = data.token || '';});
$('save').onclick = async () => {
  const {focus} = await chrome.storage.local.get('focus');
  if (focus?.end > Date.now() / 1000) return;
  await chrome.storage.local.set({token: $('token').value.trim()});
  await chrome.runtime.sendMessage({type: 'sync'});
  await status();
};
function bvid() {
  const text = $('video').value.trim();
  if (/^BV[A-Za-z0-9]{10}$/.test(text)) return text;
  const url = new URL(text);
  if (!['www.bilibili.com', 'bilibili.com', 'm.bilibili.com'].includes(url.hostname)) throw new Error('请使用 B 站完整视频链接。');
  const match = url.pathname.match(/^\/video\/(BV[A-Za-z0-9]{10})\/?$/);
  if (!match) throw new Error('未找到 BV 号，请打开视频后复制地址。');
  return match[1];
}
async function extract(collection) {
  $('output').value = '';
  try {
    const id = bvid();
    if (!collection) {
      $('output').value = id;
      $('result').textContent = '已提取 1 个视频，含该视频所有分 P。';
      return;
    }
    $('result').textContent = '正在读取合集信息…';
    const response = await fetch('https://api.bilibili.com/x/web-interface/view?bvid=' + id, {credentials: 'omit', signal: AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('B 站接口暂不可用，请手动添加各集视频链接。');
    const payload = await response.json();
    if (payload.code !== 0) throw new Error('B 站未返回视频信息，请手动添加各集视频链接。');
    const season = payload.data?.ugc_season;
    const ids = season ? (season.sections || []).flatMap(section => (section.episodes || []).map(ep => ep.bvid)) : [id];
    const clean = [...new Set(ids.filter(value => /^BV[A-Za-z0-9]{10}$/.test(value)))];
    if (!clean.length) throw new Error('未能读取合集成员，请手动添加各集视频链接。');
    $('output').value = clean.join('\n');
    $('result').textContent = `${season?.title || payload.data.title} · ${clean.length} 个视频。请核对后复制。`;
  } catch (error) {
    $('result').textContent = error.message || String(error);
  }
}
$('single').onclick = () => extract(false);
$('collection').onclick = () => extract(true);
$('copy').onclick = async () => {
  if (!$('output').value) return;
  try {await navigator.clipboard.writeText($('output').value); $('result').textContent = '已复制，请粘贴到桌面助手的允许列表。';}
  catch {$('output').select(); $('result').textContent = '请按 Ctrl+C 复制选中的列表。';}
};
status();
setInterval(status, 2000);
