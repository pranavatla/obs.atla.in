import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const fitting = html.slice(html.indexOf('  const labelOffsets ='), html.indexOf('  function frame()'));
const labels = Array.from({ length: 12 }, () => {
  const b = { style: { translate: '0px 0px' } };
  b.getBoundingClientRect = () => {
    const [x, y] = b.style.translate.split(' ').map(parseFloat);
    return { left: 135 + x, top: 140 + y, width: 110, height: 28 };
  };
  return b;
});
const fit = vm.runInNewContext(fitting + '\nfitLabels', {
  labelsBy: new Map(labels.map((b, i) => [i, b])),
  stage: { getBoundingClientRect: () => ({ left: 0, right: 360, top: 0, bottom: 320 }) },
});
fit();
const before = labels.map(b => b.style.translate);
const rects = labels.map(b => b.getBoundingClientRect());
for (let i = 0; i < rects.length; i++) {
  const a = rects[i];
  assert.ok(a.left >= 8 && a.left + a.width <= 352 && a.top >= 8 && a.top + a.height <= 312, 'Caption stays inside the mobile map');
  for (const b of rects.slice(i + 1)) {
    assert.ok(a.left + a.width <= b.left || b.left + b.width <= a.left || a.top + a.height <= b.top || b.top + b.height <= a.top, 'Captions must not overlap');
  }
}
fit();
assert.deepEqual(labels.map(b => b.style.translate), before, 'Positions remain stable across frames');
assert.ok(!html.includes('moon.add(modelLabel)'), 'Model moons share their provider caption');
assert.ok(html.includes('"model provider-group"'), 'Provider groups retain their model names');
console.log('Mobile caption packing: 12 crowded labels remain separate, onscreen, and stable; model moons share provider captions.');
