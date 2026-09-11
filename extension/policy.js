/* Pure policy shared by the worker, content guard and local regression tests. */
(function (scope) {
  function active(focus, now = Date.now() / 1000) {
    return Boolean(focus && focus.end > now);
  }
  function allowed(url, focus, now = Date.now() / 1000) {
    if (!active(focus, now)) return true;
    try {
      const u = new URL(url);
      if (!['http:', 'https:'].includes(u.protocol)) return false;
      if (!['www.bilibili.com', 'bilibili.com', 'm.bilibili.com'].includes(u.hostname)) return false;
      const m = u.pathname.match(/^\/video\/(BV[A-Za-z0-9]{10})\/?$/);
      return Boolean(m && focus.allow.includes(m[1]));
    } catch { return false; }
  }
  function rules(focus, redirectUrl, now = Date.now() / 1000) {
    if (!active(focus, now)) return [];
    const result = [{id: 1, priority: 1, action: {type: 'redirect', redirect: {url: redirectUrl}},
      condition: {requestDomains: ['bilibili.com', 'b23.tv'], resourceTypes: ['main_frame', 'sub_frame']}}];
    focus.allow.forEach((bv, index) => {
      if (!/^BV[A-Za-z0-9]{10}$/.test(bv)) throw new Error('Invalid video ID');
      result.push({id: index + 2, priority: 10, action: {type: 'allow'}, condition: {
        regexFilter: '^https?://(www\\.|m\\.)?bilibili\\.com/video/' + bv + '/?([?#].*)?$',
        isUrlFilterCaseSensitive: true, resourceTypes: ['main_frame', 'sub_frame']}});
    });
    return result;
  }
  const api = {active, allowed, rules};
  if (typeof module !== 'undefined') module.exports = api;
  else scope.FocusPolicy = api;
})(globalThis);
