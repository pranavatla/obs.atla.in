import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const ordering = html.match(/  const SITE_ORDER = .*\n  const orderSites = .*\n/)[0];
const orderSites = vm.runInNewContext(`${ordering}\norderSites`);
const expected = ['atla.in', 'gita.atla.in', 'gate.atla.in', 'obs.atla.in', 'games.atla.in', 'aif.atla.in'];
const input = [...expected].reverse().map(domain => ({ domain }));
const original = input.map(site => site.domain);
assert.deepEqual(Array.from(orderSites(input), site => site.domain), expected);
assert.deepEqual(input.map(site => site.domain), original, 'Snapshot must not be mutated');
assert.deepEqual(Array.from(orderSites([{ domain: 'new.atla.in' }, ...input]), site => site.domain), [...expected, 'new.atla.in']);
console.log('Site order checks passed');
