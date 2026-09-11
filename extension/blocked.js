async function update() {
  const {focus} = await chrome.storage.local.get('focus');
  const remaining = Math.max(0, Math.ceil((focus?.end || 0) - Date.now() / 1000));
  document.getElementById('remaining').textContent = remaining ? `${Math.floor(remaining / 60)} 分 ${remaining % 60} 秒` : '这一段专注已结束';
  document.getElementById('hint').textContent = remaining ? '结束前允许列表保持不变。' : '限制正在自动解除，可以手动打开你想访问的页面。';
}
update();
setInterval(update, 1000);
