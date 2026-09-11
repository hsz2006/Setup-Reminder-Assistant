const assert = require('node:assert/strict');
const policy = require('../extension/policy.js');
const now = 1000;
const focus = {end: 2000, allow: ['BV1234567890']};
assert.equal(policy.allowed('https://www.bilibili.com/video/BV1234567890/?p=12', focus, now), true);
assert.equal(policy.allowed('https://m.bilibili.com/video/BV1234567890', focus, now), true);
for (const url of ['https://www.bilibili.com/', 'https://www.bilibili.com/video/BV0000000000/',
  'https://www.bilibili.com/video/BV1234567890/extra', 'https://live.bilibili.com/123',
  'https://www.bilibili.com.evil/video/BV1234567890', 'https://b23.tv/abc']) {
  assert.equal(policy.allowed(url, focus, now), false, url);
}
assert.equal(policy.allowed('https://www.bilibili.com/', focus, 2000), true);
const rules = policy.rules(focus, 'chrome-extension://test/blocked.html', now);
assert.equal(rules.length, 2);
assert.equal(rules[0].action.type, 'redirect');
assert.ok(rules[1].priority > rules[0].priority);
const allowed = new RegExp(rules[1].condition.regexFilter);
assert.ok(allowed.test('https://www.bilibili.com/video/BV1234567890?p=2'));
assert.equal(allowed.test('https://www.bilibili.com/video/BV1234567890/extra'), false);
assert.deepEqual(policy.rules(focus, '', 2000), []);
console.log('Extension policy: URL boundaries, parts, strict allow list and expiry passed.');
