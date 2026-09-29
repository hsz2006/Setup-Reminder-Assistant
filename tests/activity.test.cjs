const assert = require('node:assert/strict');
const {test} = require('node:test');
const {classify} = require('../extension/activity.js');

const windowAt = (url, focused = true, state = 'normal') =>
  ({focused, state, tabs: [{active: true, url}]});

test('only the focused non-minimized window and selected tab count', () => {
  assert.equal(classify([windowAt('https://www.bilibili.com', false)]).bilibili, false);
  assert.equal(classify([windowAt('https://www.bilibili.com', true, 'minimized')]).bilibili, false);
  assert.equal(classify([{focused: true, tabs: [
    {active: false, url: 'https://www.bilibili.com'}, {active: true, url: 'https://example.org'}
  ]}]).bilibili, false);
  assert.equal(classify([windowAt('https://www.bilibili.com', false), windowAt('https://example.org')]).bilibili, false);
});

test('Bilibili domains and BV IDs are classified without reporting full URLs', () => {
  assert.deepEqual(classify([windowAt('https://www.bilibili.com/video/BV1234567890/?p=2')]),
    {focused: true, bilibili: true, video: 'BV1234567890'});
  assert.equal(classify([windowAt('https://live.bilibili.com/123')]).bilibili, true);
  assert.equal(classify([windowAt('https://b23.tv/abc')]).bilibili, true);
  assert.equal(classify([windowAt('https://bilibili.com.example.org')]).bilibili, false);
  assert.equal(classify([windowAt('chrome://newtab')]).bilibili, false);
  assert.equal(classify([]).focused, false);
});
