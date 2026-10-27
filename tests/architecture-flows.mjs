import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../assets/arch.js', import.meta.url), 'utf8');
const instrumented = source.replace(
  '  window.renderArchitecture = renderArchitecture;',
  '  window.__ARCH_TEST__ = ARCH;\n  window.renderArchitecture = renderArchitecture;',
);
const context = { window: {} };
vm.runInNewContext(instrumented, context);
const arch = context.window.__ARCH_TEST__;

const domains = ['atla.in', 'gita.atla.in', 'gate.atla.in', 'obs.atla.in', 'games.atla.in', 'aif.atla.in'];
assert.deepEqual(Object.keys(arch).sort(), domains.sort());

const tilesIn = (rows) => rows.flatMap((row) => {
  if (Array.isArray(row)) return row;
  if (row?.tiles) return row.tiles;
  if (row?.rows) return tilesIn(row.rows);
  return [];
});
const idsFor = (spec) => new Set([
  ...spec.users,
  ...tilesIn(spec.rows),
  ...(spec.security || []),
  ...tilesIn(spec.external?.rows || [spec.external?.tiles || []]),
].map((tile) => tile.id));
const edge = (domain, from, to) => arch[domain].edges.find(([a, b]) => a === from && b === to);
const main = (domain, from, to) => edge(domain, from, to)?.[3] === 1;

for (const domain of domains) {
  const ids = idsFor(arch[domain]);
  for (const [from, to] of arch[domain].edges) {
    assert.ok(ids.has(from), `${domain}: unknown edge source ${from}`);
    assert.ok(ids.has(to), `${domain}: unknown edge target ${to}`);
  }
  assert.ok(edge(domain, 'u', 'r53') || edge(domain, 'tn', 'r53'), `${domain}: DNS lookup missing`);
  for (const e of arch[domain].edges.filter(([, to]) => to === 'r53')) {
    assert.notEqual(e[3], 1, `${domain}: DNS must not be drawn as a request hop`);
  }
}

for (const domain of ['atla.in', 'obs.atla.in', 'games.atla.in', 'aif.atla.in']) {
  assert.ok(main(domain, 'u', 'cf'), `${domain}: browser-to-CloudFront HTTPS path missing`);
  assert.ok(main(domain, 'cf', 's3'), `${domain}: CloudFront-to-S3 origin path missing`);
}

assert.ok(main('gate.atla.in', 'tn', 'igw'));
for (const [from, to] of [['igw', 'eip'], ['eip', 'sg'], ['sg', 'caddy'], ['caddy', 'gw']]) {
  assert.ok(main('gate.atla.in', from, to), `gate.atla.in: missing live hop ${from} → ${to}`);
}
for (const [from, to] of [['ssm', 'gw'], ['ecr', 'gw'], ['pg', 'bk'], ['gw', 'ls']]) {
  assert.ok(edge('gate.atla.in', from, to), `gate.atla.in: missing dependency ${from} → ${to}`);
}

assert.ok(main('gita.atla.in', 'u', 'alb'));
assert.ok(main('gita.atla.in', 'alb', 'pod'));
for (const id of ['lbc', 'ing', 'svc']) assert.ok(idsFor(arch['gita.atla.in']).has(id));
for (const [from, to] of [['ing', 'lbc'], ['svc', 'ing'], ['svc', 'pod'], ['lbc', 'alb']]) {
  assert.ok(edge('gita.atla.in', from, to), `gita.atla.in: missing control path ${from} → ${to}`);
}

for (const id of ['conn', 'secret']) assert.ok(idsFor(arch['obs.atla.in']).has(id));
for (const [from, to] of [['eb', 'ad'], ['ad', 'gh'], ['gh', 'cw'], ['gh', 'gr'], ['gh', 'gs'], ['gh', 's3']]) {
  assert.ok(main('obs.atla.in', from, to), `obs.atla.in: missing refresh hop ${from} → ${to}`);
}
assert.ok(edge('obs.atla.in', 'secret', 'conn'));
assert.ok(edge('obs.atla.in', 'conn', 'ad'));
assert.equal(arch['aif.atla.in'].delivery.branch, 'master');

console.log('All six architecture specs have valid endpoints and complete live/control routes');
