/* Only report Bilibili classification and a video ID, never browsing history. */
(function (scope) {
  function classify(windows) {
    const win = windows.find(item => item.focused && item.state !== 'minimized');
    const result = {focused: Boolean(win), bilibili: false, video: ''};
    const tab = win?.tabs?.find(item => item.active);
    try {
      const url = new URL(tab?.url);
      if (!['http:', 'https:'].includes(url.protocol)) return result;
      result.bilibili = url.hostname === 'bilibili.com' || url.hostname.endsWith('.bilibili.com') || url.hostname === 'b23.tv';
      if (result.bilibili && ['bilibili.com', 'www.bilibili.com', 'm.bilibili.com'].includes(url.hostname)) {
        result.video = url.pathname.match(/^\/video\/(BV[A-Za-z0-9]{10})\/?$/)?.[1] || '';
      }
    } catch { /* A blank/internal tab is not Bilibili. */ }
    return result;
  }
  if (typeof module !== 'undefined') module.exports = {classify};
  else scope.BiliActivity = {classify};
})(globalThis);
