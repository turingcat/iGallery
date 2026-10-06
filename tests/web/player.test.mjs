import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPlayer } from '../../igallery/web/player.js';
const A = '/api/photo/00000000-0000-0000-0000-000000000001';
const B = '/api/photo/00000000-0000-0000-0000-000000000002';
function fixture(lists, fail = []) {
  const shown = [], events = [];
  let fetches = 0;
  const player = createPlayer({
    fetchList: async () => { fetches++; const list = lists[Math.min(fetches - 1, lists.length - 1)]; if (list instanceof Error) throw list; return {photos: list.map(url => ({url})), interval_seconds: 30}; },
    loadImage: async url => { events.push('load:' + url); if (fail.includes(url)) throw Error('missing'); },
    showImage: url => { shown.push(url); events.push('show:' + url); },
    wait: async ms => events.push('wait:' + ms)
  });
  return {player, shown, events, fetches: () => fetches};
}
test('loads before showing and waits between photos', async () => {
  const f = fixture([[A, B]]);
  await f.player.step(); await f.player.step();
  assert.deepEqual(f.shown, [A, B]);
  assert(f.events.indexOf('load:' + B) < f.events.indexOf('show:' + B));
  assert(f.events.indexOf('wait:30000') < f.events.indexOf('show:' + B));
});
test('single photo refreshes list and recovers changed batch', async () => {
  const f = fixture([[A], [B]]);
  await f.player.step(); await f.player.step();
  assert.deepEqual(f.shown, [A, B]); assert.equal(f.fetches(), 2);
});
test('all failed images leave current image visible and recover', async () => {
  const f = fixture([[A], [B], [A]], [B]);
  await f.player.step(); await f.player.step(); await f.player.step();
  assert.deepEqual(f.shown, [A, A]); assert(f.events.includes('wait:5000'));
});
test('empty list retries then displays', async () => {
  const f = fixture([[], [A]]); await f.player.step(); await f.player.step();
  assert.deepEqual(f.shown, [A]); assert(f.events.includes('wait:5000'));
});
test('failed refresh retains offline playlist', async () => {
  const f = fixture([[A], Error('offline')]); await f.player.step(); await f.player.step();
  assert.deepEqual(f.shown, [A, A]);
});
test('rejects remote and traversal image URLs', async () => {
  const f = fixture([['https://evil.example/image', '/api/photo/../../etc/passwd', A]]);
  await f.player.step(); assert.deepEqual(f.shown, [A]);
});
