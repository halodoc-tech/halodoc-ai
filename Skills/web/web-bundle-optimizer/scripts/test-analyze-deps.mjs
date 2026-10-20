#!/usr/bin/env node
/**
 * Self-check for the ownership gate and the fix list: `node scripts/test-analyze-deps.mjs`.
 *
 * Builds a throwaway repo in a temp dir — an owned scoped package that is packaged
 * correctly, an owned UNSCOPED package (recognised only by its repository
 * URL) with every blocker set, and two third-party packages — then asserts the two
 * rules that are easy to regress: owned packages get a fix list, packages we do not
 * own get no packaging verdict at all.
 *
 * The metafile also wires up three more scenarios, each pinning a rule the ranked
 * plan must never regress on (see the comment at each): a library-edge whose SOURCE
 * we own reaching a third-party package we don't, a third-party package that itself
 * imports a second third-party package (the row that leaked into the real run), and
 * a true-greedy re-ranking case where a candidate's marginal only turns out to be
 * the biggest once an earlier row has already landed.
 */
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const root = mkdtempSync(join(tmpdir(), 'analyze-deps-'));
const pkg = (path, json, mjs) => {
  mkdirSync(join(root, 'node_modules', path), { recursive: true });
  writeFileSync(join(root, 'node_modules', path, 'package.json'), JSON.stringify(json));
  if (mjs) writeFileSync(join(root, 'node_modules', path, 'index.mjs'), mjs);
};

// owned, scoped, and its FESM also carries a small barrel (`export { X, Y, Z }`) —
// used below to pin that a barrel split is only ever offered for owned packages.
pkg(
  '@design-system/atoms',
  { name: '@design-system/atoms', version: '1.0.0', sideEffects: false, module: 'index.mjs' },
  'export const a = 1;\nexport { X, Y, Z };\n',
);
// unscoped, so ownership can only come from the repository URL. Its FESM also
// names one symbol from each of `@design-system/atoms` and `swiper`'s barrels, which is
// what the split estimator scans for when it apportions eager bytes by usage.
pkg(
  'web-shared',
  {
    name: 'web-shared',
    version: '2.0.0',
    repository: { url: 'git@git.example.com:libs/web-shared.git' },
    module: 'index.mjs',
    dependencies: { '@angular/material': '18.0.0', moment: '2.30.0' },
  },
  "ɵɵdefineNgModule({});\nimport { X } from '@design-system/atoms';\nimport { A } from 'swiper';\n",
);
// third-party, but given a real barrel + real usage below so it would legitimately
// clear the split floor — proving it is the OWNERSHIP filter, not a lack of
// qualifying data, that keeps it out of `barrelSplits`.
pkg('swiper', { name: 'swiper', version: '11.0.0', module: 'index.mjs' }, 'export { A, B, C, D };');
pkg('@angular/material', { name: '@angular/material', version: '18.0.0' });

writeFileSync(
  join(root, 'package.json'),
  JSON.stringify({ name: 'app', dependencies: { '@design-system/atoms': '1.0.0', 'web-shared': '2.0.0', swiper: '11.0.0', '@angular/material': '18.0.0' } }),
);
writeFileSync(
  join(root, 'bundle-report.json'),
  JSON.stringify({
    eager: { raw: 1_000_000 },
    packages: [
      { name: '@design-system/atoms', raw: 140_000 },
      { name: 'web-shared', raw: 220_000 },
      { name: 'swiper', raw: 90_000 },
      { name: '@angular/material', raw: 180_000 },
      { name: 'src (app code)', raw: 370_000 },
    ],
  }),
);

// A metafile, so the ranked-plan simulator runs in the self-check too: app.ts is
// the only eager importer of the owned package, while shared.ts is reached from
// two places — the case where a naive sum double-counts a shared chunk.
mkdirSync(join(root, 'dist', 'browser'), { recursive: true });
writeFileSync(join(root, 'dist', 'browser', 'index.html'), '<script src="main.js"></script>');
writeFileSync(
  join(root, 'dist', 'browser', 'stats.json'),
  JSON.stringify({
    inputs: {
      'src/main.ts': {
        bytes: 100,
        imports: [
          { path: 'src/app.ts', kind: 'import-statement' },
          // a direct, independent path into `@design-system/atoms` — kept alive even
          // if every app edge into `web-shared` (below) is cut, which is
          // exactly what makes the library-edge rows nested under it surviveable.
          { path: 'node_modules/@design-system/atoms/index.mjs', kind: 'import-statement' },
          { path: 'src/gX.ts', kind: 'import-statement' },
          { path: 'src/gY.ts', kind: 'import-statement' },
          { path: 'src/gZ.ts', kind: 'import-statement' },
        ],
      },
      'src/app.ts': {
        bytes: 100,
        imports: [
          { path: 'node_modules/web-shared/index.mjs', kind: 'import-statement', original: 'web-shared' },
          { path: 'src/shared.ts', kind: 'import-statement' },
        ],
      },
      'src/shared.ts': { bytes: 100, imports: [] },
      // web-shared also reaches `@design-system/atoms` — a second, redundant path,
      // so cutting neither the app's direct edge nor this one alone frees atoms.
      'node_modules/web-shared/index.mjs': { bytes: 220_000, imports: [{ path: 'node_modules/@design-system/atoms/index.mjs', kind: 'import-statement' }] },
      // Scenario 1 — ownership filter on library-edge candidates: `@design-system/atoms`
      // (owned) statically reaches a third-party package heavy enough to clear the
      // floor. That edge must survive as a `library-edge` candidate with
      // `via: '@design-system/atoms'` — the target package being third-party is fine,
      // that's the whole point of the row (cut it from the OWNED library's side).
      'node_modules/@design-system/atoms/index.mjs': {
        bytes: 25_000,
        imports: [
          { path: 'node_modules/canvas-confetti/index.mjs', kind: 'import-statement' },
          { path: 'node_modules/@angular/material/index.mjs', kind: 'import-statement' },
          { path: 'node_modules/swiper/index.mjs', kind: 'import-statement' },
        ],
      },
      'node_modules/canvas-confetti/index.mjs': { bytes: 25_000, imports: [] },
      // Scenario 1b — the row that leaked in the real run: a third-party package
      // (`@angular/material`, reached only via the owned `atoms`) itself statically
      // imports a SECOND third-party package (`@angular/cdk`). Its source is not
      // ours to MR, so no candidate may ever be generated from this edge.
      'node_modules/@angular/material/index.mjs': { bytes: 300, imports: [{ path: 'node_modules/@angular/cdk/index.mjs', kind: 'import-statement' }] },
      'node_modules/@angular/cdk/index.mjs': { bytes: 22_000, imports: [] },
      // Same third-party-source shape, but reachable and big enough that, absent
      // the ownership filter on barrel splits, it would legitimately qualify —
      // scenario 2 asserts it is filtered out of `barrelSplits` all the same.
      'node_modules/swiper/index.mjs': { bytes: 30_000, imports: [] },
      // Scenario 3 — true greedy re-ranking. `gX` is the biggest standalone row and
      // is always picked first. `gZ` (21 KB standalone, smaller than `gY`'s 24 KB)
      // and `gX` both guard `gBonus` (6 KB) redundantly, so cutting either alone
      // does not free it. Once `gX` lands, `gBonus` has only `gZ` left guarding it,
      // so `gZ`'s marginal jumps to 21 KB + 6 KB = 27 KB — bigger than `gY`'s
      // untouched 24 KB. A fixed sort-by-standalone-freed walk would still rank
      // `gY` (24 KB standalone) ahead of `gZ` (21 KB standalone); true greedy must
      // rank `gZ` first because its REAL marginal, once `gX` has landed, is bigger.
      'src/gX.ts': { bytes: 50_000, imports: [{ path: 'src/gBonus.ts', kind: 'import-statement' }] },
      'src/gY.ts': { bytes: 24_000, imports: [] },
      'src/gZ.ts': { bytes: 21_000, imports: [{ path: 'src/gBonus.ts', kind: 'import-statement' }] },
      'src/gBonus.ts': { bytes: 6_000, imports: [] },
    },
    outputs: {
      'dist/browser/main.js': {
        entryPoint: 'src/main.ts',
        imports: [],
        inputs: {
          'src/main.ts': { bytesInOutput: 100 },
          'src/app.ts': { bytesInOutput: 100 },
          'src/shared.ts': { bytesInOutput: 40_000 },
          'node_modules/web-shared/index.mjs': { bytesInOutput: 220_000 },
          'node_modules/@design-system/atoms/index.mjs': { bytesInOutput: 25_000 },
          'node_modules/canvas-confetti/index.mjs': { bytesInOutput: 25_000 },
          'node_modules/@angular/material/index.mjs': { bytesInOutput: 300 },
          'node_modules/@angular/cdk/index.mjs': { bytesInOutput: 22_000 },
          'node_modules/swiper/index.mjs': { bytesInOutput: 30_000 },
          'src/gX.ts': { bytesInOutput: 50_000 },
          'src/gY.ts': { bytesInOutput: 24_000 },
          'src/gZ.ts': { bytesInOutput: 21_000 },
          'src/gBonus.ts': { bytesInOutput: 6_000 },
        },
      },
    },
  }),
);

const script = join(dirname(fileURLToPath(import.meta.url)), 'analyze-deps.mjs');
const md = execFileSync('node', [script, '--scopes', '@design-system', '--owner-hosts', 'git.example.com', '--repos-root', join(root, 'no-clones'), '--dist', 'dist', '--md', join(root, 'deps.md')], { cwd: root, encoding: 'utf8' });
const deps = JSON.parse(readFileSync(join(root, 'bundle-deps.json'), 'utf8'));
const lib = (name) => deps.libraries.find((l) => l.name === name);

// an unscoped package is owned when its manifest points at one of `--owner-hosts`
assert.ok(lib('web-shared'), 'web-shared must be recognised as owned via its repository URL');
assert.equal(lib('web-shared').diagnosis.owner, 'upstream');
assert.ok(lib('web-shared').fixes.length >= 4, 'every blocker plus the consumer item must be prescribed');
for (const f of lib('web-shared').fixes) for (const field of ['what', 'where', 'why', 'how', 'verify']) assert.ok(f[field], `missing ${field}`);

// a correctly packaged owned library still gets the one fix that applies: defer the usage
assert.equal(lib('@design-system/atoms').diagnosis.owner, 'consumer');
assert.equal(lib('@design-system/atoms').fixes.length, 1);

// a probe that could not run must read as unknown, never as a pass
const probe = lib('@design-system/atoms').packaging.shake;
assert.equal(probe.status, 'skipped', 'no esbuild in the fixture, so the probe cannot run');
assert.ok(
  lib('@design-system/atoms').diagnosis.reasons.some((r) => r.includes('unverified')),
  'a skipped probe has to be stated as unverified in the reasons',
);

// packages we do not own get no verdict and no fix block — only the "who requires it" row
assert.equal(deps.libraries.some((l) => ['swiper', '@angular/material'].includes(l.name)), false);
assert.equal(md.includes('### `swiper`'), false, 'third-party must not appear in the fix list');
assert.ok(md.includes('| `swiper` |'), 'third-party must still appear as context');
assert.ok(deps.thirdPartyOwners.find((t) => t.name === '@angular/material').requiredByInternalLibs.includes('web-shared'));
// an owned package must never be double-listed as third party
assert.equal(deps.thirdPartyOwners.some((t) => t.name === 'web-shared'), false);

// the ranked plan must be simulated, and its arithmetic must be the graph's
const plan = deps.opportunities;
assert.ok(plan.length >= 1, 'the simulator has to produce at least the package candidate');
// app.ts is the sole eager importer of everything below it, so making it lazy frees
// the package plus what only it reached: 220000 + 40000 (shared.ts) + 100 (itself)
const top = plan[0];
assert.equal(top.target, 'src/app.ts');
assert.equal(top.marginalFreed, 260_100);
assert.equal(top.cumulativeFreed, 260_100);
// "defer every app import of web-shared" frees the same bytes, so the greedy
// plan must drop it rather than sell one set of bytes twice
assert.equal(plan.some((o) => o.target === 'web-shared'), false, 'overlapping candidate must not be listed twice');
// and the same bytes must not be sold twice by a second overlapping candidate
assert.equal(
  plan.reduce((sum, o) => sum + o.marginalFreed, 0),
  plan.at(-1).cumulativeFreed,
  'marginal savings must add up to the cumulative total, never exceed it',
);
assert.ok(md.includes('Where the KB are'), 'the report must lead with the ranked plan');

// Scenario 1 — library-edge candidates are scoped to packages we own on the SOURCE
// side; the third-party target (canvas-confetti / @angular/material) is fine.
const libraryEdges = plan.filter((o) => o.kind === 'library-edge');
assert.ok(
  libraryEdges.some((o) => o.via === '@design-system/atoms'),
  'an owned library statically reaching a heavy third-party package must still be offered as a candidate',
);
assert.ok(
  libraryEdges.every((o) => ['@design-system/atoms', 'web-shared'].includes(o.via)),
  `no library-edge candidate may have a via we do not own, got: ${libraryEdges.map((o) => o.via).join(', ')}`,
);
// Scenario 1b — the leaked row: a third-party SOURCE (`@angular/material`)
// statically importing a second third-party package (`@angular/cdk`) must never
// surface as a candidate, even though the bytes clear the floor.
assert.equal(
  libraryEdges.some((o) => o.via === '@angular/material'),
  false,
  'a third-party-to-third-party edge is not a repo we can MR — it must never become a candidate',
);

// Scenario 2 — barrel splits are scoped the same way: swiper has a real barrel and
// real (partial) usage, so absent the ownership filter it would qualify; it must
// still be excluded, while the owned `@design-system/atoms` split goes through.
assert.ok(deps.barrelSplits.some((s) => s.name === '@design-system/atoms'), 'an owned barrel with partial usage must be estimated');
assert.equal(
  deps.barrelSplits.some((s) => s.name === 'swiper'),
  false,
  'a third-party barrel must never be offered as a split candidate, even with real qualifying usage data',
);
assert.ok(
  deps.barrelSplits.every((s) => ['@design-system/atoms', 'web-shared'].includes(s.name)),
  `barrelSplits must only ever name packages we own, got: ${deps.barrelSplits.map((s) => s.name).join(', ')}`,
);

// Scenario 3 — true greedy: gZ's standalone saving (21 KB) is smaller than gY's
// (24 KB), but gZ's marginal only overtakes gY's once gX's cut has already landed
// and freed gZ to also take gBonus with it. gZ must rank ahead of gY.
const gZRow = plan.find((o) => o.target === 'src/gZ.ts');
const gYRow = plan.find((o) => o.target === 'src/gY.ts');
assert.ok(gZRow && gYRow, 'both gZ and gY must survive into the plan');
assert.equal(gZRow.marginalFreed, 27_000, "gZ's marginal must include gBonus once gX has already freed gX's own guard on it");
assert.equal(gYRow.marginalFreed, 24_000, "gY never overlaps with anything, so its marginal never moves off its standalone value");
assert.ok(
  plan.indexOf(gZRow) < plan.indexOf(gYRow),
  'a candidate with the smaller standalone saving must be ranked first once its real marginal overtakes a bigger-looking one',
);

process.stdout.write('analyze-deps self-check: ok\n');
