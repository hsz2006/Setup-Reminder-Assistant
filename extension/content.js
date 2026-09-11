(() => {
  if (globalThis.__studyStartGuard) return;
  globalThis.__studyStartGuard = true;
  let focus = {};
  let style;
  function check() {
    const active = focus.end > Date.now() / 1000;
    if (!active) {
      if (style) style.remove();
      style = null;
      return;
    }
    const match = location.pathname.match(/^\/video\/(BV[A-Za-z0-9]{10})\/?$/);
    const ok = ['www.bilibili.com', 'bilibili.com', 'm.bilibili.com'].includes(location.hostname) &&
               match && focus.allow.includes(match[1]);
    if (!ok) {
      document.querySelectorAll('video,audio').forEach(media => media.pause());
      location.replace(chrome.runtime.getURL('blocked.html'));
      return;
    }
    if (!style && document.documentElement) {
      style = document.createElement('style');
      style.textContent = `
        .recommend-list-v1,.recommend-list,.recommend-container,.rec-list,.recommend-video,
        .video-page-special-card-small,.ad-report,.slide-ad-exp,.video-page-game-card-small,
        .bili-header,.bili-mini-header,.bpx-player-ending-related,.bpx-player-ending-related-list,
        #comment,.comment-m,.reply-wrap,.reply-box,.bili-dyn-home--member,.v-popover-content {display:none!important}
      `;
      document.documentElement.appendChild(style);
    }
  }
  chrome.storage.local.get('focus').then(data => {focus = data.focus || {}; check();});
  chrome.storage.onChanged.addListener(changes => {
    if (changes.focus) {focus = changes.focus.newValue || {}; check();}
  });
  chrome.runtime.onMessage.addListener(message => {
    if (message.type === 'focus') {focus = message.focus || {}; check();}
  });
  setInterval(check, 250);
})();
