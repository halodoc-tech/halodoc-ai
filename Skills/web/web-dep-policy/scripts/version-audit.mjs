#!/usr/bin/env node
// Version-bump audit: current repo versions vs the central dependency policy.
// Run from the repo root. No dependencies beyond node >= 18 + npm + tar on PATH.
//
//   node version-audit.mjs [--registry https://npm.your-org.internal/] [--json]
//
// Fetches the newest policy from the registry (rc channel while no stable
// exists), then for every governed dependency the repo declares prints:
//   dep | declared | locked | policy | catalog | bump classification
// MAJOR bumps are flagged loudly — they need an explicit remediate-or-exception
// decision before the dep is converted to a catalog: pointer.

import { execSync } from 'node:child_process';
import { readFileSync, existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
const argVal = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : dflt;
};
const REGISTRY = argVal('--registry', 'https://npm.your-org.internal/');
const AS_JSON = args.includes('--json');
const PKG = '@your-org/pnpm-plugin-dep-version-policy';

const sh = (cmd) => execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();

// ── 1. Resolve the policy version + integrity (rc channel in bootstrap mode) ──
let tags;
try {
  tags = JSON.parse(sh(`npm view ${PKG} dist-tags --json --registry ${REGISTRY}`));
} catch (e) {
  console.error(`Cannot reach ${REGISTRY} for ${PKG} — is the VPN up and the registry configured?`);
  process.exit(2);
}
const stableIsReal = tags.latest && !tags.latest.includes('-');
const policyVersion = stableIsReal ? tags.latest : (tags.rc || tags.latest);
const integrity = sh(`npm view ${PKG}@${policyVersion} dist.integrity --registry ${REGISTRY}`);
const pinString = `${policyVersion}+${integrity}`;

// ── 2. Pull policy.json out of a published tarball ──
const fetchPolicyJson = (version) => {
  const tmp = mkdtempSync(join(tmpdir(), 'dep-policy-'));
  try {
    sh(`npm pack ${PKG}@${version} --registry ${REGISTRY} --pack-destination ${tmp}`);
    const tarball = sh(`ls ${tmp}/*.tgz`).split('\n')[0];
    sh(`tar -xzf ${tarball} -C ${tmp}`);
    return JSON.parse(readFileSync(join(tmp, 'package', 'policy.json'), 'utf8'));
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
};
const policy = fetchPolicyJson(policyVersion);
const parseVer = (v) => {
  const m = String(v || '').match(/(\d+)\.(\d+)\.(\d+)/);
  return m ? m.slice(1, 4).map(Number) : null;
};
const classify = (cur, target) => {
  const a = parseVer(cur), b = parseVer(target);
  if (!a || !b) return 'UNKNOWN';
  const level = a[0] !== b[0] ? 'MAJOR' : a[1] !== b[1] ? 'MINOR' : a[2] !== b[2] ? 'PATCH' : 'SAME';
  if (level === 'SAME') return level;
  // Direction matters: the policy pinning BELOW the repo's current version
  // means the repo would downgrade on onboarding — riskier than an upgrade
  // and usually a signal to revisit the policy version instead.
  const down = a[0] > b[0] || (a[0] === b[0] && (a[1] > b[1] || (a[1] === b[1] && a[2] > b[2])));
  return down ? `${level} DOWNGRADE` : level;
};

const stripNotes = (o) => Object.fromEntries(Object.entries(o || {}).filter(([k]) => !k.startsWith('$')));
const GLOBAL = stripNotes(policy.catalog);
const CLUSTERS = stripNotes(policy.catalogs); // { ng21: {...}, ng19: {...} }
// NOTE: there is no cluster registry. A repo's cluster is DERIVED from its
// @angular/core major (policy.json catalogs.$note; policy-core.ts currentAngularMajor).
// The install-time guard only fails on a MISMATCH between the derived cluster and
// the catalog:<name> a repo references. The sole allowlist in the policy is for
// exceptionCatalogs, which is unrelated.

// ── 3. Read the repo ──
const pj = JSON.parse(readFileSync('package.json', 'utf8'));
const declared = { ...pj.dependencies, ...pj.devDependencies };
const repoName = pj.name;

// Onboarding + pin status: an onboarded repo pins the policy in
// pnpm-workspace.yaml. A stale pin means the repo enforces an OLD policy —
// the CI gate will fail it, and the fix is the update flow.
let wsText = '';
try { wsText = readFileSync('pnpm-workspace.yaml', 'utf8'); } catch {}
// Quoting-agnostic on purpose. `pnpm add --config` writes a single-quoted key
// with an UNQUOTED value:  '@your-org/...': 1.0.0-rc.8+sha512-...
// while a hand-authored pin is usually fully double-quoted. All forms are valid
// YAML, and a double-quote-only matcher reported a correctly onboarded repo as
// NOT ONBOARDED — skipping every check the script exists to perform.
const wsPin = wsText.match(
  /^[ \t]*['"]?@your-org\/pnpm-plugin-dep-version-policy['"]?:[ \t]*['"]?([^+'"\s]+)\+([^'"\s]+)/m,
);
// pnpm keeps settings where the repo already keeps them, so when package.json
// has a `pnpm` section (commonly a CVE override) the pin is written THERE and
// pnpm-workspace.yaml is left untouched. Such a repo is genuinely governed.
const pjPinRaw = (pj.pnpm && pj.pnpm.configDependencies && pj.pnpm.configDependencies[PKG]) || null;
const pjPin = pjPinRaw ? String(pjPinRaw).match(/^([^+]+)\+(.+)$/) : null;
const pinMatch = wsPin || pjPin;
const onboarded = !!pinMatch;
const pinnedVersion = pinMatch ? pinMatch[1] : null;
const pinStale = onboarded && pinnedVersion !== policyVersion;
const pinLocation = wsPin ? 'pnpm-workspace.yaml' : pjPin ? 'package.json#pnpm.configDependencies' : null;
// Both present and disagreeing is the silent-no-op repin: pnpm resolves the
// pnpm-workspace.yaml entry and ignores the package.json copy, so `pnpm add
// --config` can report success while the app stays on the old policy.
const pinConflict = !!(wsPin && pjPin && wsPin[1] !== pjPin[1]);

// When the pin is stale, diff the PINNED policy against the LATEST one: these
// are the version movements the update will pull in — majors here need the
// same remediate-or-exception decision as onboarding-time majors.
let policyDelta = [];
if (pinStale) {
  let oldPolicy = null;
  try { oldPolicy = fetchPolicyJson(pinnedVersion); } catch { /* pinned version may be unpublished */ }
  if (oldPolicy) {
    const flat = (p) => {
      const out = {};
      for (const [d, v] of Object.entries(stripNotes(p.catalog))) out[`${d}default`] = v;
      for (const [c, entries] of Object.entries(stripNotes(p.catalogs)))
        for (const [d, v] of Object.entries(stripNotes(entries))) out[`${d}${c}`] = v;
      return out;
    };
    const a = flat(oldPolicy), b = flat(policy);
    for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
      if (a[key] === b[key]) continue;
      const [dep, catalogName] = key.split('');
      policyDelta.push({
        dep, catalog: catalogName, from: a[key] || null, to: b[key] || null,
        bump: a[key] && b[key] ? classify(a[key], b[key]) : (b[key] ? 'ADDED' : 'REMOVED'),
        referencedByRepo: String(declared[dep] || '').startsWith('catalog:'),
      });
    }
  }
}
const ngCore = declared['@angular/core'] || '';
const ngMajor = (String(ngCore).match(/(\d+)/) || [])[1] || null;
const derivedCluster = ngMajor && CLUSTERS[`ng${ngMajor}`] ? `ng${ngMajor}` : null;

// Locked (resolved) versions from the lockfile importers section — tolerant of
// both v6 and v9 formats; falls back to the declared range if not found.
let lockText = '';
try { lockText = readFileSync('pnpm-lock.yaml', 'utf8'); } catch {}
const lockedVersionOf = (dep) => {
  const esc = dep.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  // importer entry:  <dep>:\n  specifier: ...\n  version: X(peers)
  // The name must start right after line-leading whitespace, or "eslint"
  // happily matches inside "angular-eslint".
  const m = lockText.match(new RegExp(`\\n\\s+(?:'|")?${esc}(?:'|")?:\\n\\s+specifier:[^\\n]*\\n\\s+version: ([^\\s(]+)`));
  return m ? m[1] : null;
};

// ── 4. Compare ──
const rows = [];
const addRows = (catalogName, entries) => {
  for (const [dep, policyVer] of Object.entries(entries)) {
    if (!(dep in declared)) continue;
    const spec = declared[dep];
    if (String(spec).startsWith('catalog:')) {
      // Onboarded — but verify the pointer actually resolves to the POLICY
      // version. A repo-local catalog entry (e.g. auto-created by
      // catalogMode prefer/strict) or a wrong catalog name silently shadows
      // the central value while package.json still LOOKS governed.
      const locked = lockedVersionOf(dep);
      const faithful = !locked || locked === policyVer;
      rows.push({ dep, declared: spec, locked, policy: policyVer, catalog: catalogName,
        bump: faithful ? 'ALREADY ONBOARDED' : 'MISMATCH (onboarded)' });
      continue;
    }
    const locked = lockedVersionOf(dep) || String(spec).replace(/^[~^>=<\s]*/, '');
    rows.push({ dep, declared: spec, locked, policy: policyVer, catalog: catalogName, bump: classify(locked, policyVer) });
  }
};
addRows('default', GLOBAL);
// Cluster deps are compared only against the repo's OWN cluster, derived from its
// Angular major — the same rule the install-time guard applies.
// Comparing against every cluster produces bogus MAJOR flags (e.g. an ng21 repo
// "downgrading" to the ng19 catalog it will never reference).
const ownCluster = derivedCluster;
if (ownCluster) addRows(ownCluster, stripNotes(CLUSTERS[ownCluster]));
else if (Object.keys(CLUSTERS).length) {
  const inAnyCluster = Object.values(CLUSTERS).flatMap((e) => Object.keys(stripNotes(e)));
  const present = [...new Set(inAnyCluster)].filter((d) => d in declared);
  if (present.length)
    console.error(`note: repo matches no policy cluster (angular ${ngMajor || '?'}); cluster-governed deps present but not compared: ${present.join(', ')}`);
}

// ── 5. Report ──
const order = { MISMATCH: 0, MAJOR: 0, MINOR: 1, PATCH: 2, UNKNOWN: 3, SAME: 4, ALREADY: 5 };
const rank = (b) => order[b.split(' ')[0]] ?? 3;
rows.sort((x, y) => rank(x.bump) - rank(y.bump) || x.dep.localeCompare(y.dep));
const result = {
  policyPackage: PKG,
  policyVersion,
  pin: pinString,
  channel: stableIsReal ? 'stable' : 'rc (bootstrap — no stable published yet)',
  repo: repoName,
  mode: onboarded ? 'UPDATE' : 'ONBOARD',
  pinnedVersion,
  pinLocation,
  pinConflict,
  pinStatus: onboarded ? (pinStale ? 'STALE' : 'CURRENT') : 'NOT ONBOARDED',
  policyDelta,
  angularMajor: ngMajor,
  derivedCluster,
  clusterDepsPresent: rows.some((r) => r.catalog !== 'default'),
  rows,
};
if (AS_JSON) {
  console.log(JSON.stringify(result, null, 2));
  process.exit(0);
}
console.log(`policy: ${PKG}@${policyVersion}  [${result.channel}]`);
console.log(`pin for pnpm-workspace.yaml:\n  "${PKG}": "${pinString}"\n`);
console.log(`repo: ${repoName}  |  @angular/core major: ${ngMajor || '?'}  |  cluster (derived): ${derivedCluster || `none — no ng${ngMajor || '?'} catalog in policy`}`);
if (!onboarded) {
  console.log(`mode: ONBOARD — repo has no policy config dependency yet.`);
} else if (pinStale) {
  console.log(`mode: UPDATE — PIN STALE: pinned ${pinnedVersion}, newest is ${policyVersion}. The CI gate will fail this repo until the pin is bumped.`);
  if (policyDelta.length) {
    console.log(`policy changes between ${pinnedVersion} and ${policyVersion} (an update pulls these in):`);
    for (const d of policyDelta) {
      const mark = d.referencedByRepo ? ' <-- referenced by this repo via catalog:' : '';
      const flag = String(d.bump).startsWith('MAJOR') && d.referencedByRepo ? ' FLAG: remediate it, or record an exceptionCatalogs entry — there is no per-dep defer' : '';
      console.log(`  ${d.dep} [${d.catalog}]: ${d.from ?? '(absent)'} -> ${d.to ?? '(removed)'}  ${d.bump}${mark}${flag}`);
    }
  } else {
    console.log(`no governed-version changes between ${pinnedVersion} and ${policyVersion} (or the pinned version's tarball is gone) — the update is a pin+checksum bump only.`);
  }
} else {
  console.log(`mode: UPDATE — pin is CURRENT (${pinnedVersion}); nothing to bump.`);
}
if (pinConflict) {
  console.log(`!! CONFLICTING PINS — pnpm-workspace.yaml has ${wsPin[1]}, package.json#pnpm.configDependencies has ${pjPin[1]}.`);
  console.log(`   pnpm resolves the pnpm-workspace.yaml entry, so the package.json copy is IGNORED and that repin never took effect.`);
  console.log(`   Fix: delete pnpm.configDependencies from package.json and keep the pin only in pnpm-workspace.yaml.`);
} else if (pinLocation === 'package.json#pnpm.configDependencies') {
  console.log(`!! PIN IS IN package.json (pnpm.configDependencies), not pnpm-workspace.yaml.`);
  console.log(`   pnpm honours it there, but it is the wrong location: pnpm documents configDependencies in pnpm-workspace.yaml,`);
  console.log(`   the CI gate and this script expect it there, and if a workspace entry is ever added the package.json one`);
  console.log(`   silently loses. Fix: move the whole \`pnpm\` block to pnpm-workspace.yaml, then re-run the pin command.`);
}
if (result.clusterDepsPresent && !derivedCluster)
  console.log(`!! repo declares cluster-governed deps but policy has no catalog for Angular ${ngMajor || '?'} — they cannot be pointed at catalog:<cluster> until one exists (a policy MR adds it). Global-only onboarding is still fine.`);
console.log('');
if (!rows.length) { console.log('No governed dependencies found in this repo — onboarding would add only the toolchain pin + config dependency.'); process.exit(0); }
const w = (s, n) => String(s ?? '-').padEnd(n);
console.log(w('DEP', 34) + w('DECLARED', 14) + w('LOCKED', 12) + w('POLICY', 12) + w('CATALOG', 10) + 'BUMP');
for (const r of rows) {
  const flag = r.bump.startsWith('MAJOR') ? '  <-- FLAG: remediate it, or record an exceptionCatalogs entry — there is no per-dep defer'
    : r.bump.startsWith('MISMATCH') ? '  <-- FLAG: catalog: pointer resolves OFF-POLICY — check for a repo-local catalog entry shadowing the central one, or a wrong catalog name'
    : '';
  console.log(w(r.dep, 34) + w(r.declared, 14) + w(r.locked, 12) + w(r.policy, 12) + w(r.catalog, 10) + r.bump + flag);
}
const majors = rows.filter((r) => r.bump.startsWith('MAJOR')).length;
console.log(`\nsummary: ${rows.length} governed dep(s) present — ${majors} MAJOR, ` +
  `${rows.filter((r) => r.bump.startsWith('MINOR')).length} minor, ${rows.filter((r) => r.bump.startsWith('PATCH')).length} patch, ` +
  `${rows.filter((r) => r.bump === 'SAME').length} same, ${rows.filter((r) => r.bump === 'ALREADY ONBOARDED').length} already onboarded, ${rows.filter((r) => r.bump.startsWith('MISMATCH')).length} onboarded-but-MISMATCHED.`);
const deltaMajors = policyDelta.filter((d) => String(d.bump).startsWith('MAJOR') && d.referencedByRepo).length;
const mismatches = rows.filter((r) => r.bump.startsWith('MISMATCH')).length;
if (mismatches) console.log(`!! ${mismatches} onboarded dep(s) resolve OFF-POLICY — fix before trusting the catalog pointers.`);
if (majors || deltaMajors || mismatches) process.exitCode = 1; // scriptable signal: needs a human decision
