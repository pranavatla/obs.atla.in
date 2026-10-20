import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const tokens = selector => Object.fromEntries([...html.match(selector)[1].matchAll(/(--[\w-]+):\s*(#[\da-f]{6});/g)].map(([, key, value]) => [key, value]));
const dark = tokens(/:root \{([\s\S]*?)\n  \}/);
const light = { ...dark, ...tokens(/:root\[data-theme="light"\] \{([\s\S]*?)\n  \}/) };
const luminance = hex => {
  const rgb = hex.slice(1).match(/../g).map(x => parseInt(x, 16) / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
};
for (const [theme, palette] of Object.entries({ dark, light })) {
  for (const [foreground, background] of [['--on-accent', '--accent'], ['--text-muted', '--surface-raised'], ['--text-subtle', '--surface'], ['--text-subtle', '--surface-raised']]) {
    const a = luminance(palette[foreground]), b = luminance(palette[background]);
    assert.ok((Math.max(a, b) + .05) / (Math.min(a, b) + .05) >= 4.5, `${theme}: ${foreground} on ${background} fails AA`);
  }
}
const themeScript = html.match(/<script>([\s\S]*?)<\/script>/)[1];
for (const [saved, systemDark, expected] of [[null, false, 'light'], [null, true, 'dark'], ['light', true, 'light'], ['dark', false, 'dark']]) {
  const document = { documentElement: { dataset: {} } };
  vm.runInNewContext(themeScript, { document, localStorage: { getItem: () => saved }, matchMedia: () => ({ matches: systemDark }) });
  assert.equal(document.documentElement.dataset.theme, expected);
}
for (const script of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(script[1]);
console.log('Contrast, theme preference, and JavaScript syntax checks passed');
