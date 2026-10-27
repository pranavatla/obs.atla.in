import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const fitting = html.slice(html.indexOf('  const labelOffsets ='), html.indexOf('  function frame()'));
const labels = [100, 130].map(left => {
  const b = { style: { translate: '0px 0px' } };
  b.getBoundingClientRect = () => ({ left: left + parseFloat(b.style.translate), top: 100, width: 80, height: 20 });
  return b;
});
const fit = vm.runInNewContext(fitting + '\nfitLabels', {
  labelsBy: new Map(labels.map((b, i) => [i, b])),
  stage: { getBoundingClientRect: () => ({ left: 0, right: 360, top: 0, bottom: 320 }) },
});
fit();
assert.ok(labels.every(b => b.style.translate === '0px 0px'), 'In-bounds names remain at their projected objects');
assert.ok(!html.includes('label-leaders'), 'No annotation guide lines');
assert.ok(!html.includes('moon.add(modelLabel)'), 'No separate orbiting model captions');
assert.ok(html.includes('.lbl.provider-group small { display: none; }'), 'Model lists stay out of diagram captions');
assert.ok(html.includes('Models in the gateway catalog'), 'Full model names remain available in the detail panel');
console.log('Map captions stay anchored, with short provider names and no annotation lines; model details remain available.');
