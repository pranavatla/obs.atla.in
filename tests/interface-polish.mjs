import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
for (const name of ['index.html', 'classic.html']) {
  const page = fs.readFileSync(new URL('../' + name, import.meta.url), 'utf8');
  for (const match of page.matchAll(/<script(?: type="(module)")?>([\s\S]*?)<\/script>/g)) {
    const result = spawnSync(process.execPath, ['--input-type=' + (match[1] || 'commonjs'), '--check'], { input: match[2], encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
  }
}

// Projection correction must keep labels onscreen without accumulating an offset each frame.
const fitting = html.slice(html.indexOf('  const labelOffsets ='), html.indexOf('  function frame()'));
const labels = [-50, 350].map(left => {
  const label = { style: { translate: '0px 0px' } };
  label.getBoundingClientRect = () => ({ left: left + parseFloat(label.style.translate), top: 20, width: 120, height: 44 });
  return label;
});
const fit = vm.runInNewContext(fitting + '\nfitLabels', { labelsBy: new Map(labels.map((b, i) => [i, b])), stage: { getBoundingClientRect: () => ({left:0,right:390,top:0,bottom:844}) }, innerWidth: 390, innerHeight: 844 });
fit();
assert.equal(labels[0].style.translate, '58px 0px');
assert.equal(labels[1].style.translate, '-88px 0px');
fit();
assert.equal(labels[0].style.translate, '58px 0px');
assert.equal(labels[1].style.translate, '-88px 0px');

// A closed sheet must remove its controls from keyboard navigation and return focus.
const closing = html.match(/  function closePanel\(\) \{[\s\S]*?\n  \}/)[0];
let focused = false, marked = false, shifted = true;
const context = vm.createContext({
  selected: { kind: 'site', id: 'gita.atla.in' }, flight: {},
  labelsBy: new Map([['site:gita.atla.in', { focus: () => { focused = true; } }]]),
  panel: { inert: false, contains: () => true, classList: { remove: () => {} } },
  document: { activeElement: {}, querySelectorAll: () => [] }, markSelected: () => { marked = true; }, setViewShift: on => { shifted = on; },
});
vm.runInContext(closing + '\nclosePanel()', context);
assert.equal(context.panel.inert, true);
assert.equal(context.selected, null);
assert.equal(context.flight, null);
assert.ok(focused && marked && !shifted);
console.log('Both page scripts parse; label clamping is stable; sheet close restores focus and cancels flight');

// Device motion preference overrides the page's resume control.
const syncing = html.match(/  const syncMotion = \(\) => \{[\s\S]*?\n  \};/)[0];
for (const [reduceMotion, motionPaused, expected] of [[false, false, 'on'], [false, true, 'off'], [true, false, 'off']]) {
  const state = { document: { documentElement: { dataset: {} } }, motionBtn: { setAttribute() {} }, railIcon() {}, controls: { autoRotate: true }, reduceMotion, motionPaused };
  vm.runInNewContext(syncing + '\nsyncMotion()', state);
  assert.equal(state.document.documentElement.dataset.motion, expected);
  assert.equal(state.motionBtn.disabled, reduceMotion);
  assert.equal(state.controls.autoRotate, false);
}
console.log('Pause/resume respects device motion preferences and keeps automatic camera rotation disabled');

// Switching top-level tabs must not hide the nested AI model group.
const classic = fs.readFileSync(new URL('../classic.html', import.meta.url), 'utf8');
const showSource = classic.slice(classic.indexOf('  const show ='), classic.indexOf('  tabs.forEach((t) => t.addEventListener'));
const sections = [{ id:'overview', hidden:false }, { id:'ai', hidden:true }], nested = {hidden:false};
const tabState = { current:'overview', snapshot:null, tabs:sections.map(s => ({dataset:{tab:s.id},setAttribute(){}})), document:{querySelectorAll:selector => selector === '.wrap > section.page' ? sections : [...sections,nested]}, history:{replaceState(){}}, location:{pathname:'/classic.html'} };
vm.runInNewContext(showSource + '\nshow("ai", true)',tabState);
assert.equal(sections[0].hidden,true);
assert.equal(sections[1].hidden,false);
assert.equal(nested.hidden,false);

// Small model costs retain the snapshot's microunit precision, so visible parts reconcile.
const formatting = html.slice(html.indexOf('  const nf ='), html.indexOf('  const IST ='));
const format = vm.runInNewContext(formatting + '\nfmt', {Intl});
const amount = value => Math.round(Number(format(value,'usd').slice(1).replaceAll(',','')) * 1e6);
assert.equal(amount(.195679) + amount(.078135), amount(.273814));
assert.equal(format(13808,'count'),'13,808');
assert.equal(format(null,'count'),'—');
console.log('AI tab keeps nested content visible; displayed costs reconcile; counts and missing values remain honest');
