#!/usr/bin/env node
/**
 * analyze-deps.mjs — attribute the eager set to the *repositories that own it*.
 *
 * `analyze-bundle.mjs` answers "which package do these eager bytes belong to?".
 * That is not enough to plan the work: in a typical org most of the eager set belongs
 * to internal libraries published from a handful of shared repos, and a fix may
 * belong upstream in that repo rather than in the app. This script answers:
 *
 *   1. which repo owns each eager byte (`@design-system/*` -> libs/design-system, …);
 *   2. whether the cost is caused by how the library is *packaged* (upstream fix)
 *      or by how the app *uses* it (local fix);
 *   3. which internal library dragged in each eager third-party package.
 *
 * Usage:
 *   node analyze-deps.mjs [--report bundle-report.json] [--pkg package.json]
 *        [--node-modules node_modules] [--repos-root ..]
 *        [--scopes @design-system,@web-shared,@your-org] [--owner-hosts git.example.com]
 *        [--out bundle-deps.json]
 *        [--md bundle-deps.md] [--no-probe]
 *
 *   node analyze-deps.mjs --trace <package> [--dist dist]
 *        every eager importer of one package, app code and libraries separately —
 *        run this before any defer candidate, because a chunk leaves the eager set
 *        only when its LAST eager importer does.
 *
 * Everything is read-only and dependency-free. Exit codes: 0 ok, 1 usage/IO error.
 */
import { readFileSync, writeFileSync, existsSync, readdirSync, rmSync } from 'node:fs';
import { join, dirname, resolve, basename } from 'node:path';
import { homedir } from 'node:os';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let esbuildCache;

const args = parseArgs(process.argv.slice(2));

const reportPath = args.report ?? 'bundle-report.json';
const pkgPath = args.pkg ?? 'package.json';
const nodeModules = args['node-modules'] ?? 'node_modules';
const reposRoot = expandHome(args['repos-root'] ?? '..');
const scopes = (args.scopes ?? '').split(',').map((s) => s.trim()).filter(Boolean);
const ownerHosts = (args['owner-hosts'] ?? '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);

if (!existsSync(reportPath)) fail(`bundle report not found: ${reportPath} — run analyze-bundle.mjs first`);
if (!existsSync(pkgPath)) fail(`package.json not found: ${pkgPath}`);

const report = JSON.parse(readFileSync(reportPath, 'utf8'));
const appPkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
const eagerByPackage = new Map((report.packages ?? []).map((p) => [p.name, p.raw]));

const declared = { ...(appPkg.dependencies ?? {}), ...(appPkg.devDependencies ?? {}) };
const installedCache = new Map();
const internalNames = Object.keys(declared).filter(isOwned);
if (!internalNames.length) {
  process.stderr.write(`analyze-deps: no owned packages found in ${pkgPath} — nothing to attribute\n`);
}

// --trace answers the one question that decides whether deferring a component
// will free anything: who *else* still reaches this package eagerly?
if (args.trace) {
  const statsPath = args.stats ?? findStats(args.dist ?? 'dist');
  if (!statsPath) fail('--trace needs the metafile; pass --stats <path> or --dist <dir>');
  process.stdout.write(traceImporters(JSON.parse(readFileSync(statsPath, 'utf8')), args.trace, args.dist ?? 'dist'));
  process.exit(0);
}

const sourceIndex = indexLocalRepos(reposRoot);
// The metafile is what turns "defer the usage" into "defer these three files, and
// note the seven libraries that also hold it eager". Without it the fix list can
// only state the pattern, which is the difference between a report a developer can
// act on and one they have to redo by hand.
const distDir = args.dist ?? 'dist';
const statsPath = args.stats ?? findStats(distDir);
const metafile = statsPath ? JSON.parse(readFileSync(statsPath, 'utf8')) : null;
const eagerSet = metafile ? eagerOutputs(metafile, distDir) : null;
const libs = internalNames.map((name) => inspect(name, declared[name]));
const repos = groupByRepo(libs);
const thirdParty = attributeThirdParty(libs);

const ranked = metafile ? rankOpportunities(metafile, distDir) : { plan: [], blocked: [], splits: [] };

const out = {
  schema: 1,
  eagerRaw: report.eager?.raw ?? 0,
  eagerGzip: report.eager?.gzip ?? 0,
  reposRoot,
  scopes,
  repos,
  libraries: libs,
  thirdPartyOwners: thirdParty,
  opportunities: ranked.plan,
  blockedFromAppCode: ranked.blocked,
  barrelSplits: ranked.splits ?? [],
};

if (args.out !== false) writeJson(args.out ?? 'bundle-deps.json', out);
const md = renderMarkdown(out);
if (args.md !== false) writeText(args.md ?? 'bundle-deps.md', md);
process.stdout.write(md);

// ---------------------------------------------------------------------------

/**
 * Packaging facts that decide whether the eager cost is the library's fault.
 *
 * A library that is correctly packaged for tree-shaking (`sideEffects: false`,
 * subpath `exports`, flat ESM, no NgModules) cannot be improved by changing how
 * the app imports it — esbuild already drops what the app does not use, so the
 * only lever left is deferring the *usage*. These flags are only the claim; the
 * shake probe below is what confirms it. The inverse is also true and is the
 * finding worth escalating: a library missing `sideEffects: false` forces every
 * byte of every imported entry point into the bundle no matter how little of it
 * the app touches.
 */
function inspect(name, declaredRange) {
  const dir = join(nodeModules, name);
  const installed = readInstalled(name);
  const source = sourceIndex.get(name) ?? null;

  const eagerRaw = eagerByPackage.get(name) ?? 0;
  const publishedRaw = installed ? publishedSize(dir) : 0;
  const facts = installed
    ? {
        version: installed.version ?? null,
        sideEffects: installed.sideEffects ?? null,
        subpathExports: exportSubpaths(installed.exports),
        moduleFormat: installed.module || installed.fesm2022 || installed.exports ? 'esm' : 'unknown',
        ngModuleCount: countNgModules(dir),
        publishedRaw,
        retainedPct: publishedRaw && eagerRaw ? Number(((eagerRaw / publishedRaw) * 100).toFixed(0)) : null,
        dependencies: Object.keys(installed.dependencies ?? {}),
        peerDependencies: Object.keys(installed.peerDependencies ?? {}),
        shake: eagerRaw >= prescribeFloor() ? probeShaking(name, dir) : null,
      }
    : null;

  return {
    name,
    declaredRange,
    installed: Boolean(installed),
    eagerRaw,
    shareOfEagerPct: report.eager?.raw ? Number(((eagerRaw / report.eager.raw) * 100).toFixed(1)) : 0,
    repo: source?.repo ?? null,
    repoRemote: source?.remote ?? null,
    sourcePath: source?.path ?? null,
    packaging: facts,
    diagnosis: facts ? diagnose(facts, eagerRaw) : { owner: 'unknown', reasons: ['package not installed — run the install first'] },
    importers: metafile && eagerRaw > 0 ? importersOf(metafile, name, eagerSet) : null,
    fixes: facts && eagerRaw >= prescribeFloor() ? prescribe(name, facts, eagerRaw, source, metafile && eagerRaw > 0 ? importersOf(metafile, name, eagerSet) : null) : [],
  };
}

/**
 * Ownership gate. Everything downstream — packaging verdicts, upstream findings,
 * the per-dependency fix list — applies ONLY to packages your org publishes.
 *
 * A packaging defect in a package we do not own is not a finding: nobody here can
 * add `sideEffects: false` to it, and "fork it" is not a recommendation. Those
 * packages still appear in the report, but as context under "who requires them",
 * where the only real lever is deferring the code that imports them.
 *
 * Owned means: a declared internal scope (`@design-system`, `@web-shared`, `@your-org`, …),
 * or a manifest whose repository/homepage points at one of `--owner-hosts`. The second
 * test is what catches unscoped names (`design-system`, `web-shared`) and any new
 * scope nobody remembered to pass to `--scopes`.
 */
function isOwned(name) {
  if (scopes.some((s) => name === s || name.startsWith(`${s}/`))) return true;
  const installed = readInstalled(name);
  if (!installed) return false;
  const repo = installed.repository;
  return [typeof repo === 'string' ? repo : repo?.url, installed.homepage, installed.publishConfig?.registry]
    .filter((u) => typeof u === 'string')
    .some((u) => ownerHosts.some((h) => u.toLowerCase().includes(h)));
}

function readInstalled(name) {
  if (!installedCache.has(name)) {
    const manifest = join(nodeModules, name, 'package.json');
    let value = null;
    try {
      value = existsSync(manifest) ? JSON.parse(readFileSync(manifest, 'utf8')) : null;
    } catch {
      /* an unparsable manifest is treated as not installed */
    }
    installedCache.set(name, value);
  }
  return installedCache.get(name);
}

/**
 * The per-dependency work list: for each owned library in the eager set, what to
 * change, in which file, why it costs bytes, and the command that proves it.
 *
 * The diagnosis says who owns the fix; this says what the fix *is*. A developer
 * reading `sideEffects is not false — upstream` still has to know that the edit
 * is one line in the library's package.json, that it needs a version bump and a
 * consumer update, and that the proof is the retained-% falling in the next
 * metafile. Without that the finding gets read, agreed with, and not done.
 */
function prescribe(name, facts, eagerRaw, source, importers) {
  const at = source?.path ? `${source.path}/package.json` : `the library's \`package.json\` in ${source?.repo ?? 'its source repo'}`;
  const kb = `${(eagerRaw / 1024).toFixed(1)} KB`;
  const out = [];

  if (facts.sideEffects !== false) {
    out.push({
      tier: 'upstream',
      what: 'Add `"sideEffects": false` to the published manifest',
      where: at,
      why: `currently \`${JSON.stringify(facts.sideEffects)}\`, so esbuild must assume every module the app touches has an import-time effect and keeps all ${kb} — including exports nothing renders`,
      how: 'set it in the library project\'s `package.json` (ng-packagr copies it into `dist`); if any module really does run work on import, list those files instead of `false` rather than dropping the flag',
      verify: 'publish/link the new version, rebuild the app with `--stats-json`, re-run `analyze-bundle.mjs` — the package\'s eager bytes and retained % must both fall',
    });
  }
  if (facts.shake?.broken) {
    out.push({
      tier: 'upstream',
      what: 'Split the barrel — publish secondary entry points (or per-component chunks) so one symbol can be imported alone',
      where: source?.path ? `\`${source.path}/src/public-api.ts\` plus a per-entry-point \`ng-package.json\`` : "the library's `public-api.ts` and `ng-package.json`",
      why: `importing only \`${facts.shake.symbol}\` retains ${kbOf(facts.shake.oneSymbolRaw)} of the ${kbOf(facts.shake.wholeBarrelRaw)} barrel (${facts.shake.retainedPct}%), which is why ${kb} of it is eager here. The published output is one module, so \`sideEffects: false\` cannot drop anything and every consumer of any symbol pays for all of it`,
      how: 'give the leaf pieces consumers actually import alone (services, models, enums, tokens) their own entry point — an `ng-package.json` in a subfolder, exported as `<pkg>/<name>` — or stop re-exporting everything from one `public-api.ts`. Keep the root barrel re-exporting them so nothing breaks',
      verify: 're-run this script: the shake probe must report the one-symbol cost well under the barrel, and the app\'s eager bytes for this package drop once the consumer switches to the subpath import',
    });
  }
  if (facts.ngModuleCount > 0) {
    out.push({
      tier: 'upstream',
      what: `Ship standalone components instead of the ${facts.ngModuleCount} NgModule(s) in the output`,
      where: source?.path ?? 'the library source',
      why: 'importing one component from an NgModule pulls in every other declaration that module lists, whether or not the app renders it — the module is one indivisible unit to the bundler',
      how: 'mark the components `standalone: true` and export them directly; keep the NgModule as a thin deprecated re-export for one release so consumers migrate without a breaking change',
      verify: '`analyze-deps.mjs` reports `NgModules: 0` and the eager bytes drop by the declarations the app never used',
    });
  }

  const heavy = facts.dependencies.filter((d) => heavyThirdParty().some((h) => d === h || d.startsWith(`${h}/`)));
  if (heavy.length) {
    out.push({
      tier: 'upstream',
      what: `Stop hard-depending on ${heavy.map((h) => `\`${h}\``).join(', ')}`,
      where: at,
      why: 'every consumer inherits it whether or not it uses the part of the library that needs it, so the cost is charged to apps that never asked for it',
      how: 'move it to `peerDependencies` + `peerDependenciesMeta.optional`, isolate the code that needs it behind a secondary entry point, or replace it (`moment` → `date-fns`/`Intl`, `crypto-js` → Web Crypto, `lodash` → the two functions actually used)',
      verify: 're-run `analyze-deps.mjs`: the package leaves this library\'s `dependencies` row, and `analyze-bundle.mjs` shows it out of the eager set once no other eager library requires it',
    });
  }

  const blocked = importers?.libs.length ?? 0;
  out.push({
    tier: out.length
      ? 'consumer (do this too — packaging alone will not move it)'
      : blocked
        ? 'consumer — blocked: this package cannot leave the eager set on its own'
        : 'consumer',
    what: blocked
      ? `Defer the whole cluster that holds \`${name}\` eager — ${blocked} library importer(s) plus the app files below`
      : `Defer the app code that puts \`${name}\` in the eager graph`,
    where: importers
      ? formatImporters(importers)
      : 'this repo — `main.ts`, the root component template, or `root-routes.ts` (no metafile available, so the importers could not be listed — pass `--dist`)',
    why: out.length
      ? 'a packaging fix shrinks what ships; it does not stop the package from loading before the first paint'
      : `packaged correctly for tree-shaking, so what ships is exactly what the app references — the only lever left is when it loads (${kb} today)`,
    how: blocked
      ? `deferring only the app files above frees nothing — a chunk leaves the eager set when its LAST eager importer does. Either defer the listed libraries in the same change (they are usually shell UI: header, footer, mega-menu, modals → \`@defer (on viewport|on interaction)\`), or drop this package as a candidate and pick one with no library importer.`
      : 'apply the matching playbook pattern to the files above — `@defer (on viewport|on interaction)` for shell UI, `loadComponent`/`loadChildren` for route-scoped code, a dynamic `import()` for a bootstrap-time `register()` call',
    verify: `\`node scripts/analyze-deps.mjs --trace ${name} --dist dist\` must list **no** remaining eager library importer, then re-measure: the package has to *leave* the "packages that moved" table, not merely shrink`,
  });

  return out;
}

/** Measured, not inferred — and a skipped probe must read as unknown, never as a pass. */
function shakeCell(shake) {
  if (!shake) return '—';
  if (shake.status !== 'ok') return 'not measured';
  return shake.broken ? `**no — ${shake.retainedPct}%**` : `yes (${shake.retainedPct}%)`;
}

function kbOf(bytes) {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

/** Which repo owns a `library-edge`/split row's edit — never throws for a package we haven't cloned. */
function repoOf(pkg) {
  const source = sourceIndex.get(pkg);
  if (!source) return pkg;
  return source.remote ?? (source.repo ? basename(source.repo) : pkg);
}

/** The importer lists, trimmed to what fits in a report line. */
function formatImporters(importers) {
  const show = (list, limit) => {
    const head = list.slice(0, limit).map((f) => `\`${f}\``).join(', ');
    return list.length > limit ? `${head} (+${list.length - limit} more)` : head;
  };
  const parts = [];
  parts.push(importers.app.length ? `app code — ${show(importers.app, 6)}` : 'app code — none, this package is reached only through other libraries');
  if (importers.libs.length) parts.push(`**also held eager by** ${show(importers.libs, 8)}`);
  return parts.join('; ');
}

/**
 * Does tree-shaking actually work on this package?
 *
 * `sideEffects: false` and "no NgModules" are necessary, not sufficient, and
 * trusting them produced a wrong verdict on a real repo: `@design-system/templates` has
 * both, and importing its two-member enum still retained 341 KB —
 * every one of its 19 components. ng-packagr had emitted the whole library as ONE
 * internal chunk module which the barrel re-exports, and `sideEffects: false` only
 * licenses dropping unused *modules*. With one module there is nothing to drop.
 *
 * So measure it instead of inferring it: bundle one symbol, bundle the whole
 * barrel, compare. A ratio near 1 means the entry point is indivisible, which is
 * the one situation where "add secondary entry points" IS the fix rather than a
 * pointless refactor.
 *
 * Everything else in this script is a file read; this shells out to the repo's own
 * esbuild. When it cannot be resolved the probe is skipped and says so — a missing
 * probe must never read as a pass.
 */
function probeShaking(name, dir) {
  if (args.probe === 'false' || args['no-probe']) return { status: 'skipped', reason: 'disabled with --no-probe' };
  const esbuild = loadEsbuild();
  if (!esbuild) return { status: 'skipped', reason: 'esbuild not resolvable from this repo — run the probe where the app is installed' };

  const entryName = pickProbeSymbol(dir, name);
  if (!entryName) return { status: 'skipped', reason: 'no named export found in the published output' };

  // Externalise everything except the package under test, so the number is this
  // library's own bytes and not its dependency tree's.
  const external = ['@angular/*', 'rxjs', 'tslib', ...Object.keys(declared).filter((d) => d !== name)];
  const probeFile = `.analyze-deps-probe-${name.replace(/[^a-z0-9]/gi, '-')}.mjs`;

  const build = (source) => {
    writeFileSync(probeFile, source);
    const result = esbuild.buildSync({ entryPoints: [probeFile], bundle: true, minify: true, format: 'esm', write: false, platform: 'browser', external, logLevel: 'silent' });
    return result.outputFiles[0].contents.length;
  };

  try {
    const one = build(`import { ${entryName} } from '${name}';
console.log(${entryName});
`);
    const all = build(`import * as probe from '${name}';
console.log(probe);
`);
    const retainedPct = all ? Number(((one / all) * 100).toFixed(0)) : null;
    return { status: 'ok', symbol: entryName, oneSymbolRaw: one, wholeBarrelRaw: all, retainedPct, broken: all > 50 * 1024 && retainedPct >= 80 };
  } catch (error) {
    return { status: 'skipped', reason: `probe build failed: ${String(error.message ?? error).split('\n')[0]}` };
  } finally {
    try {
      rmSync(probeFile, { force: true });
    } catch {
      /* nothing to clean up */
    }
  }
}

/**
 * A symbol whose cost should be near zero if shaking works: prefer a service, model
 * or enum over a component, because a component legitimately drags its template's
 * dependencies with it and would make a working library look broken.
 */
function pickProbeSymbol(dir, name) {
  const all = exportedSymbols(join(dir, readInstalled(name)?.module ?? ''));
  return all.find((n) => !/(Component|Directive|Pipe|Module)$/.test(n)) ?? all[0] ?? null;
}

/** The repo's own esbuild — hoisted install first, then pnpm's virtual store. */
function loadEsbuild() {
  if (esbuildCache !== undefined) return esbuildCache;
  esbuildCache = null;
  const candidates = [resolve(nodeModules, 'esbuild')];
  for (const entry of safeReaddir(join(nodeModules, '.pnpm'))) {
    if (entry.name.startsWith('esbuild@')) candidates.push(resolve(nodeModules, '.pnpm', entry.name, 'node_modules', 'esbuild'));
  }
  for (const candidate of candidates) {
    if (!existsSync(join(candidate, 'package.json'))) continue;
    try {
      esbuildCache = require(candidate);
      break;
    } catch {
      /* try the next candidate */
    }
  }
  return esbuildCache;
}

/**
 * `owner` is where the fix has to happen. Deliberately conservative: a library
 * becomes an upstream finding only on a defect that actually blocks the bundler.
 *
 * The trap this exists to avoid: reporting "no subpath exports" as a defect. A
 * flat single-entry-point library with `sideEffects: false` and ESM output is
 * fully tree-shakeable — esbuild drops unused top-level symbols from one FESM
 * just as well as from ten entry points. Recommending deep-path imports there
 * costs a refactor across every consumer and saves nothing. Missing subpaths
 * matter only when something else already prevents shaking.
 */
function diagnose(facts, eagerRaw) {
  const blockers = [];
  const notes = [];

  const shakeable = facts.sideEffects === false && facts.moduleFormat === 'esm';
  if (facts.sideEffects !== false) {
    blockers.push('`sideEffects` is not `false` — the bundler must assume every imported module matters, so unused exports still ship');
  }
  if (facts.ngModuleCount > 0) {
    blockers.push(`${facts.ngModuleCount} NgModule(s) in the published output — importing one pulls in every declaration it lists, whether rendered or not`);
  }
  if (facts.shake?.broken) {
    blockers.push(
      `**tree-shaking does not work on this entry point** — importing only \`${facts.shake.symbol}\` retains ${kbOf(facts.shake.oneSymbolRaw)} of the ${kbOf(facts.shake.wholeBarrelRaw)} barrel (${facts.shake.retainedPct}%), measured with the repo's esbuild. The published output is effectively one indivisible module, so \`sideEffects: false\` has nothing to drop`,
    );
  } else if (facts.shake?.status === 'skipped') {
    notes.push(`shake probe skipped (${facts.shake.reason}) — packaging is unverified here, not verified good`);
  } else if (facts.shake?.status === 'ok') {
    notes.push(`shake probe: one symbol (\`${facts.shake.symbol}\`) costs ${kbOf(facts.shake.oneSymbolRaw)} of a ${kbOf(facts.shake.wholeBarrelRaw)} barrel (${facts.shake.retainedPct}%) — the entry point does divide`);
  }

  const heavy = facts.dependencies.filter((d) => heavyThirdParty().some((h) => d === h || d.startsWith(`${h}/`)));
  if (heavy.length) {
    blockers.push(`declares ${heavy.map((h) => `\`${h}\``).join(', ')} as a hard dependency — every consumer inherits it`);
  }

  if (facts.subpathExports === 0) {
    notes.push(
      shakeable && !facts.shake?.broken
        ? 'single entry point, but `sideEffects: false` + ESM means it is still tree-shaken per symbol — deep-path imports would change nothing'
        : 'single entry point, and with shaking measurably blocked a consumer cannot import one symbol in isolation — **this is the case where secondary entry points are the fix**',
    );
  }
  if (facts.retainedPct !== null) {
    notes.push(
      `${facts.retainedPct}% of the published bytes survive into the eager set (raw published vs minified eager, so minification alone accounts for roughly half of any drop — read this as a direction, not a shaking score)`,
    );
  }

  if (blockers.length) return { owner: 'upstream', reasons: [...blockers, ...notes] };
  if (eagerRaw === 0) return { owner: 'none', reasons: ['not in the eager set'] };
  return {
    owner: 'consumer',
    reasons: [
      'packaged correctly for tree-shaking (`sideEffects: false`, ESM, no NgModules) — what ships is what the app references, so the lever is deferring the *usage*, not repackaging the library',
      ...notes,
    ],
  };
}

// A function, not a `const`: the analysis runs above these declarations, where a
// `const` would still be in its temporal dead zone.
/**
 * Below this, a package is noise in a 2.5 MB eager set: a fix block for 3 KB costs
 * more attention than the bytes are worth, and fourteen near-identical blocks bury
 * the four that matter. Small packages are still listed, just in one line.
 */
function prescribeFloor() {
  return 20 * 1024;
}

function heavyThirdParty() {
  return ['crypto-js', 'moment', 'moment-timezone', 'lodash', 'swiper', 'chart.js', 'pdfjs-dist', 'ua-parser-js', '@angular/material', '@angular/cdk'];
}

/**
 * Which internal library requires each eager third-party package. Both
 * `dependencies` and `peerDependencies` count: a peer the app satisfies is still
 * a package the app cannot remove while that library is in the eager graph.
 *
 * This is the question a per-package size table cannot answer. `@angular/material`
 * being the largest eager package looks like an app-level problem until you see
 * that five internal libraries require it, at which point removing it is a
 * cross-repo negotiation, not a refactor.
 */
function attributeThirdParty(libs) {
  const rows = [];
  for (const [name, raw] of eagerByPackage) {
    if (name === 'src (app code)' || internalNames.includes(name)) continue;
    if (['rxjs', 'zone.js', 'tslib', '@angular/core', '@angular/common', '@angular/router', '@angular/forms', '@angular/platform-browser'].includes(name)) continue;
    if (raw < 20 * 1024) continue;

    const requiredBy = libs
      .filter((l) => l.packaging && [...l.packaging.dependencies, ...l.packaging.peerDependencies].includes(name))
      .map((l) => l.name);
    const direct = Object.hasOwn(appPkg.dependencies ?? {}, name);
    rows.push({
      name,
      raw,
      declaredByApp: direct,
      requiredByInternalLibs: requiredBy,
      owner: requiredBy.length ? (direct ? 'shared — app + internal libs' : 'internal library') : direct ? 'app' : 'transitive (deeper)',
    });
  }
  return rows.sort((a, b) => b.raw - a.raw);
}

function groupByRepo(libs) {
  const byRepo = new Map();
  for (const lib of libs) {
    const key = lib.repo ?? 'unresolved (source repo not cloned locally)';
    const entry = byRepo.get(key) ?? { repo: key, remote: lib.repoRemote ?? null, eagerRaw: 0, packages: [], upstreamFindings: 0 };
    entry.eagerRaw += lib.eagerRaw;
    if (lib.eagerRaw > 0) entry.packages.push(lib.name);
    if (lib.diagnosis.owner === 'upstream' && lib.eagerRaw > 0) entry.upstreamFindings++;
    byRepo.set(key, entry);
  }
  return [...byRepo.values()]
    .map((r) => ({ ...r, shareOfEagerPct: report.eager?.raw ? Number(((r.eagerRaw / report.eager.raw) * 100).toFixed(1)) : 0 }))
    .sort((a, b) => b.eagerRaw - a.eagerRaw);
}

/**
 * What would actually leave the eager set, in KB, if a given import edge stopped
 * being static.
 *
 * Everything else in this report explains *why* bytes are eager. This answers the
 * only question a developer starts from — where do I get the KB, and how many —
 * and it answers it by simulation rather than estimate: cut the edges a change
 * would cut, recompute reachability over the metafile's own module graph, and sum
 * the eager bytes that are no longer reachable. A candidate whose libraries still
 * hold the package scores ~0 KB here, which is the last-eager-importer rule
 * enforced by arithmetic instead of by a warning nobody reads.
 *
 * These numbers are still projections — only a rebuild is proof — but they are
 * projections from the real graph, not from a pattern's "usually saves" note.
 */
function rankOpportunities(metafile, distDir) {
  const eager = eagerOutputs(metafile, distDir);
  const weight = new Map();
  for (const name of eager) {
    for (const [input, info] of Object.entries(metafile.outputs[name]?.inputs ?? {})) {
      weight.set(input, (weight.get(input) ?? 0) + (info.bytesInOutput ?? 0));
    }
  }

  const edges = new Map();
  for (const [file, info] of Object.entries(metafile.inputs)) {
    const targets = new Set();
    for (const imp of info.imports ?? []) {
      if (imp.kind === 'dynamic-import' || imp.external) continue;
      if (metafile.inputs[imp.path]) targets.add(imp.path);
    }
    edges.set(file, targets);
  }

  const roots = [...eager].map((name) => metafile.outputs[name]?.entryPoint).filter((entry) => entry && metafile.inputs[entry]);
  const reach = (cut) => {
    const seen = new Set();
    const queue = [...roots];
    while (queue.length) {
      const file = queue.pop();
      if (seen.has(file)) continue;
      seen.add(file);
      for (const target of edges.get(file) ?? []) {
        if (!cut.has(`${file}|${target}`)) queue.push(target);
      }
    }
    return seen;
  };

  const baseline = reach(new Set());
  const bytesFreed = (cut) => {
    const after = reach(cut);
    let freed = 0;
    for (const [file, bytes] of weight) if (baseline.has(file) && !after.has(file)) freed += bytes;
    return freed;
  };

  // The unit of work is an IMPORT EDGE, not a file. The app shell — `main.ts`,
  // `app.config.ts`, `app.component.ts` — cannot be lazy-loaded; it is the root.
  // Ranking "load app.component.ts lazily" produced a plan claiming 85% of the
  // eager set, which is arithmetically true and impossible to execute. What the
  // developer can actually change is what those files import: a static import
  // becomes a dynamic `import()`, a template usage becomes `@defer`, a bootstrap
  // provider moves to route-level `providers`.
  const candidates = [];
  const appFiles = [...baseline].filter((f) => f.startsWith('src/'));

  const byFileAndPackage = new Map();
  for (const file of appFiles) {
    for (const target of edges.get(file) ?? []) {
      const pkg = packageOf(target);
      if (!pkg || pkg === 'src' || isFramework(pkg)) continue;
      const key = `${file}|${pkg}`;
      if (!byFileAndPackage.has(key)) byFileAndPackage.set(key, { file, pkg, cut: new Set() });
      byFileAndPackage.get(key).cut.add(`${file}|${target}`);
    }
  }

  for (const { file, pkg, cut } of byFileAndPackage.values()) {
    const freed = bytesFreed(cut);
    if (freed < prescribeFloor()) continue;
    candidates.push({
      kind: 'edge',
      label: `in \`${file}\`, stop importing \`${pkg}\` statically`,
      target: pkg,
      file,
      cut: [...cut],
      freed,
    });
  }

  // A package several app files import needs all of those edges cut together, which
  // is a different (larger) candidate than any one of them.
  const eagerByPkg = new Map();
  for (const [file, bytes] of weight) {
    if (!baseline.has(file)) continue;
    const pkg = packageOf(file);
    if (pkg) eagerByPkg.set(pkg, (eagerByPkg.get(pkg) ?? 0) + bytes);
  }

  const byPackage = new Map();
  for (const { file, pkg, cut } of byFileAndPackage.values()) {
    if (!byPackage.has(pkg)) byPackage.set(pkg, { files: new Set(), cut: new Set() });
    byPackage.get(pkg).files.add(file);
    for (const edge of cut) byPackage.get(pkg).cut.add(edge);
  }
  for (const [pkg, { files, cut }] of byPackage) {
    if (files.size < 2) continue;
    const freed = bytesFreed(cut);
    if (freed < prescribeFloor()) continue;
    candidates.push({
      kind: 'package',
      label: `stop importing \`${pkg}\` statically in all ${files.size} app files that reach it`,
      target: pkg,
      files: [...files],
      cut: [...cut],
      freed,
    });
  }

  // The same simulation, one level up: an edge whose SOURCE is a library is an edit
  // in that library's repo. Without these rows the plan silently stops at the app
  // boundary and reads as "12.9% is all there is", when most of the eager set is
  // held by library-to-library edges that only the owning repo can cut.
  const byLibraryEdge = new Map();
  for (const from of baseline) {
    const fromPkg = packageOf(from);
    if (!fromPkg || fromPkg === 'src' || isFramework(fromPkg)) continue;
    for (const target of edges.get(from) ?? []) {
      const toPkg = packageOf(target);
      if (!toPkg || toPkg === 'src' || toPkg === fromPkg || isFramework(toPkg)) continue;
      const key = `${fromPkg}|${toPkg}`;
      if (!byLibraryEdge.has(key)) byLibraryEdge.set(key, { fromPkg, toPkg, cut: new Set() });
      byLibraryEdge.get(key).cut.add(`${from}|${target}`);
    }
  }
  for (const { fromPkg, toPkg, cut } of byLibraryEdge.values()) {
    // The report is scoped to packages your org owns: a third-party SOURCE (e.g.
    // `@angular/material` importing `@angular/cdk`) is not a repo we can send an MR
    // to, so it must never surface as a row even though the bytes are real.
    if (!internalNames.includes(fromPkg)) continue;
    const freed = bytesFreed(cut);
    if (freed < prescribeFloor()) continue;
    candidates.push({
      kind: 'library-edge',
      label: `in \`${fromPkg}\`, stop importing \`${toPkg}\` statically`,
      target: toPkg,
      via: fromPkg,
      cut: [...cut],
      freed,
    });
  }

  // App files that are NOT the bootstrap shell can genuinely become lazy — a
  // component behind `@defer`, a route behind `loadComponent`.
  for (const file of appFiles) {
    if (!weight.has(file) || isShell(file)) continue;
    const cut = new Set();
    for (const [from, targets] of edges) if (targets.has(file) && baseline.has(from)) cut.add(`${from}|${file}`);
    if (!cut.size) continue;
    const freed = bytesFreed(cut);
    if (freed >= prescribeFloor()) {
      candidates.push({ kind: 'file', label: `load \`${file}\` lazily (\`@defer\` / \`loadComponent\` / dynamic \`import()\`)`, target: file, cut: [...cut], freed });
    }
  }

  // Greedy cumulative plan: re-simulate with the previous cuts already applied, so
  // overlapping candidates cannot be counted twice. Two candidates that free the
  // same shared chunk are worth one saving, not two, and only a re-simulation
  // knows that.
  //
  // Sorting once by standalone `freed` and then walking that fixed order is NOT
  // greedy: standalone `freed` is each candidate's saving with nothing else cut
  // yet, but after row 1 is applied, shared chunks it already freed no longer
  // count toward anyone else's marginal — the ranking can (and did) flip. Every
  // iteration has to re-score every remaining candidate against what is already
  // `applied` and take the true max, not trust a ranking computed before any cuts
  // existed.
  const applied = new Set();
  const remaining = [...candidates];
  const plan = [];
  while (remaining.length && plan.length < 8) {
    const before = bytesFreed(applied);
    let bestIndex = -1;
    let bestMarginal = -Infinity;
    remaining.forEach((candidate, index) => {
      const merged = new Set([...applied, ...candidate.cut]);
      const marginal = bytesFreed(merged) - before;
      if (marginal > bestMarginal) {
        bestMarginal = marginal;
        bestIndex = index;
      }
    });
    if (bestMarginal < prescribeFloor()) break;
    const [candidate] = remaining.splice(bestIndex, 1);
    candidate.marginalFreed = bestMarginal;
    candidate.cumulativeFreed = before + bestMarginal;
    plan.push(candidate);
    for (const edge of candidate.cut) applied.add(edge);
  }

  // Edge cuts cannot model the other upstream lever. Splitting a barrel does not
  // change *reachability* — `@design-system/atoms` stays eager because the shell renders
  // one icon — it changes how many bytes come along for the ride. So estimate that
  // separately, from the symbols its eager importers actually name.
  const splits = [];
  for (const [pkg, eagerBytes] of eagerByPkg) {
    // Scoped to packages your org owns, same as the library-edge rows above: we
    // cannot MR a barrel split into `@angular/animations`.
    if (pkg === 'src' || eagerBytes < prescribeFloor() || isFramework(pkg) || !internalNames.includes(pkg)) continue;
    const estimate = estimateSplit(pkg, eagerBytes, baseline);
    if (estimate) splits.push(estimate);
  }
  splits.sort((a, b) => b.estimatedSaving - a.estimatedSaving);

  // The other half of the answer: eager packages that NO app-side edit can free.
  // Without this the plan reads as "12.9% is all there is", when in fact 30% of the
  // eager set sits behind library-to-library edges and an upstream barrel split.
  const blocked = [];
  const planned = new Set(plan.map((candidate) => candidate.target));
  for (const [pkg, eagerBytes] of eagerByPkg) {
    if (pkg === 'src' || eagerBytes < prescribeFloor() || isFramework(pkg) || planned.has(pkg)) continue;
    // Measured against the pristine graph, not against `applied` — asking "what
    // would cutting these edges free" after already cutting them answers 0 KB and
    // libels a workable candidate as blocked.
    const entry = byPackage.get(pkg) ?? { cut: new Set(), files: new Set() };
    const freed = bytesFreed(entry.cut);
    if (freed >= prescribeFloor()) continue;
    blocked.push({ name: pkg, eagerBytes, appEdges: entry.files.size ?? 0, freedIfAllAppEdgesCut: freed });
  }
  blocked.sort((a, b) => b.eagerBytes - a.eagerBytes);

  return { plan: plan.map(({ cut, ...rest }) => rest), blocked, splits };
}

/**
 * How much of a barrel is dead weight for the consumers that hold it eager.
 *
 * Method, and its limits: collect the symbols every eager importer names in its
 * `import { … } from '<pkg>'` — app sources and the installed FESMs of library
 * importers alike, since a library's published output states its imports plainly —
 * and compare that count against the barrel's total exports. The saving is
 * apportioned by symbol COUNT, not by bytes, so it is an estimate and labelled as
 * one: twelve icons and one 40 KB carousel do not weigh the same.
 *
 * It is still the only number available for this lever, and the direction is never
 * in doubt — the shake probe already proved a single symbol retains the whole
 * barrel, so the unused share is pure waste.
 */
function estimateSplit(pkg, eagerBytes, baseline) {
  const installed = readInstalled(pkg);
  if (!installed?.module) return null;
  const total = exportedSymbols(join(nodeModules, pkg, installed.module)).length;
  if (!total) return null;

  const used = new Set();
  const pattern = new RegExp(`import\\s*(?:type\\s*)?\\{([^}]*)\\}\\s*from\\s*['"]${pkg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:/[^'"]*)?['"]`, 'g');
  for (const file of baseline) {
    const owner = packageOf(file);
    if (owner === pkg) continue;
    const path = file.startsWith('src/') ? file : file.replace(/^.*node_modules\//, `${nodeModules}/`);
    if (!existsSync(path)) continue;
    let source;
    try {
      source = readFileSync(path, 'utf8');
    } catch {
      continue;
    }
    for (const match of source.matchAll(pattern)) {
      for (const part of match[1].split(',')) {
        const symbol = part.trim().split(/\s+as\s+/)[0].trim();
        if (symbol) used.add(symbol);
      }
    }
  }
  if (!used.size || used.size >= total) return null;

  const unusedShare = 1 - used.size / total;
  return {
    name: pkg,
    eagerBytes,
    usedSymbols: used.size,
    totalSymbols: total,
    estimatedSaving: Math.round(eagerBytes * unusedShare),
  };
}

/** Named exports of a barrel, from its own re-export statements. */
function exportedSymbols(entry) {
  if (!existsSync(entry)) return [];
  const names = new Set();
  for (const block of readFileSync(entry, 'utf8').matchAll(/export\s*\{([^}]*)\}/g)) {
    for (const part of block[1].split(',')) {
      const symbol = part.trim().split(/\s+as\s+/).pop()?.trim();
      if (symbol && /^[A-Za-z_$][\w$]*$/.test(symbol) && symbol !== 'default') names.add(symbol);
    }
  }
  return [...names];
}

/**
 * Framework packages are the floor; ranking them as opportunities wastes the
 * reader's time. A function, not a `const` — the analysis runs above these
 * declarations, where a `const` would still be in its temporal dead zone.
 */
function isFramework(pkg) {
  return ['@angular/core', '@angular/common', '@angular/router', '@angular/forms', '@angular/platform-browser', 'rxjs', 'zone.js', 'tslib'].includes(pkg);
}

/**
 * The bootstrap shell. These files load before anything else by definition, so
 * "make it lazy" is not a change that exists for them — only their imports are.
 */
function isShell(file) {
  return /^src\/(main|main\.server)\.ts$/.test(file) || /^src\/app\/app(\.[a-z-]+)?\.(ts|config\.ts|component\.ts)$/.test(file) || /\bapp\.(config|component|provider\.config|routes)\.ts$/.test(file);
}

/** node_modules path -> package name; app sources collapse to `src`. */
function packageOf(file) {
  if (file.startsWith('src/')) return 'src';
  const match = file.match(/node_modules\/(?:\.pnpm\/[^/]+\/node_modules\/)?(@[^/]+\/[^/]+|[^/]+)/);
  return match ? match[1] : null;
}

/**
 * Index every locally cloned repo's library projects by published package name,
 * so a finding can name the repo and path an upstream MR would touch. Angular
 * workspaces keep libraries under projects/ | libs/ | packages/.
 */
function indexLocalRepos(root) {
  const index = new Map();
  if (!existsSync(root)) return index;

  for (const repo of safeReaddir(root)) {
    const repoPath = join(root, repo.name);
    if (!repo.isDirectory()) continue;
    for (const container of ['projects', 'libs', 'packages']) {
      const containerPath = join(repoPath, container);
      if (!existsSync(containerPath)) continue;
      for (const project of safeReaddir(containerPath)) {
        if (!project.isDirectory()) continue;
        const manifest = join(containerPath, project.name, 'package.json');
        if (!existsSync(manifest)) continue;
        try {
          const { name } = JSON.parse(readFileSync(manifest, 'utf8'));
          if (name && !index.has(name)) index.set(name, { repo: repoPath, path: dirname(manifest), remote: gitRemote(repoPath) });
        } catch {
          /* an unparsable manifest is not worth failing the run over */
        }
      }
    }
  }
  return index;
}

function gitRemote(repoPath) {
  const config = join(repoPath, '.git', 'config');
  if (!existsSync(config)) return null;
  const match = readFileSync(config, 'utf8').match(/url\s*=\s*(\S+)/);
  if (!match) return null;
  return match[1].replace(/^.*[:/]([^/]+\/[^/]+?)(\.git)?$/, '$1');
}

function exportSubpaths(exportsField) {
  if (!exportsField || typeof exportsField !== 'object') return 0;
  return Object.keys(exportsField).filter((k) => k.startsWith('./') && k !== './package.json').length;
}

/** Total published ESM bytes, the denominator for "how much of this library ships". */
function publishedSize(dir) {
  let total = 0;
  for (const file of findFiles(dir, /\.mjs$/, 3)) {
    try {
      total += readFileSync(file).length;
    } catch {
      /* unreadable file contributes nothing */
    }
  }
  return total;
}

/** NgModules survive into the published FESM as `ɵɵdefineNgModule` calls. */
function countNgModules(dir) {
  let count = 0;
  for (const file of findFiles(dir, /\.mjs$/, 3)) {
    const text = readFileSync(file, 'utf8');
    count += (text.match(/ɵɵdefineNgModule|defineNgModule\(/g) ?? []).length;
  }
  return count;
}

function findFiles(dir, pattern, depth) {
  if (depth < 0 || !existsSync(dir)) return [];
  const found = [];
  for (const entry of safeReaddir(dir)) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) found.push(...findFiles(path, pattern, depth - 1));
    else if (pattern.test(entry.name)) found.push(path);
  }
  return found;
}

function safeReaddir(dir) {
  try {
    return readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }
}

function renderMarkdown(out) {
  const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
  const lines = ['# Eager bytes by owning repository', ''];

  lines.push(`Eager JS total: **${kb(out.eagerRaw)}**. Internal scopes: ${out.scopes.join(', ')}.`, '');

  const barrelSplits = out.barrelSplits ?? [];
  if (out.opportunities?.length || barrelSplits.length) {
    const gzipRatio = out.eagerGzip && out.eagerRaw ? out.eagerGzip / out.eagerRaw : null;
    // The app's own repo, for `edge`/`package`/`file` rows — read from git, not from
    // the package name (`appPkg.name` is a package id like `my-app`, not a repo).
    const appRepoLabel = gitRemote('.') ?? appPkg.name;
    lines.push(
      '## Where the KB are — ranked, simulated on the module graph',
      '',
      'One table, both repos: **simulated** rows are graph-accurate edge cuts — a static import that',
      'becomes a dynamic `import()`, a template usage that becomes `@defer`, a bootstrap provider that',
      'moves to route-level `providers` — cutting exactly that import edge and recomputing what is still',
      'reachable from the eager entry points. **Cumulative** re-simulates with the rows above already',
      'applied, so two edits that free the same shared chunk are counted once; it only ever runs over the',
      'simulated rows. **estimate** rows apportion a barrel\'s eager bytes by symbol count — a direction,',
      'not a promise, since the graph does not change shape until the barrel is actually split — and are',
      'appended after, unable to join that cumulative chain because they do not cut a reachability edge.',
      'The **Repo** column says whose MR the row belongs in: this app for `edge`/`package`/`file` rows,',
      'the owning library repo for `library-edge` and estimate rows — both scoped to packages your org',
      'owns, never a third party we cannot send an MR to. The app shell (`main.ts`, `app.config.ts`,',
      '`app.component.ts`) is never itself a row: it cannot be lazy — only its imports can. Projections',
      'from the real graph; a rebuild is still the proof.',
      '',
      `| # | Repo | Change | Leaves eager | ${gzipRatio ? 'gzip est. | ' : ''}Eager before | Eager after | Cumulative | Type |`,
      `| ---: | --- | --- | ---: | ${gzipRatio ? '---: | ' : ''}---: | ---: | ---: | --- |`,
    );
    // Before/after are stated per row and cumulatively, because "−157 KB" alone
    // never answers the question the number is asked in service of: what does the
    // eager set weigh when this lands, and how far is that from the target.
    out.opportunities.forEach((o, i) => {
      const repo = o.kind === 'library-edge' ? `\`${repoOf(o.via)}\`` : `\`${appRepoLabel}\``;
      const gzipCell = gzipRatio ? `${kb(o.marginalFreed * gzipRatio)} | ` : '';
      const before = out.eagerRaw - (o.cumulativeFreed - o.marginalFreed);
      lines.push(
        `| ${i + 1} | ${repo} | ${o.label} | ${kb(o.marginalFreed)} | ${gzipCell}${kb(before)} | ${kb(before - o.marginalFreed)} | ${kb(o.cumulativeFreed)} | simulated |`,
      );
    });
    let row = out.opportunities?.length ?? 0;
    for (const s of barrelSplits) {
      row += 1;
      const gzipCell = gzipRatio ? `${kb(s.estimatedSaving * gzipRatio)} | ` : '';
      lines.push(
        `| ${row} | \`${repoOf(s.name)}\` | split the \`${s.name}\` barrel so consumers import only what they use ` +
          `(${s.usedSymbols} of ${s.totalSymbols} exports are referenced) | ${kb(s.estimatedSaving)} | ${gzipCell}— | — | — | estimate (by symbol count) |`,
      );
    }
    lines.push('');
    // The before/after summary only ever covers the simulated chain — there is
    // nothing to summarise when the plan is empty (e.g. only barrel splits qualified).
    if (out.opportunities?.length) {
      const total = out.opportunities.at(-1).cumulativeFreed;
      lines.push(
        '| Eager JS | Before | After all rows | Delta |',
        '| --- | ---: | ---: | ---: |',
        `| raw | ${kb(out.eagerRaw)} | ${kb(out.eagerRaw - total)} | **−${kb(total)} (−${((total / out.eagerRaw) * 100).toFixed(1)}%)** |`,
        ...(gzipRatio
          ? [`| gzip (est.) | ${kb(out.eagerGzip)} | ${kb(out.eagerGzip - total * gzipRatio)} | **−${kb(total * gzipRatio)} (−${((total / out.eagerRaw) * 100).toFixed(1)}%)** |`]
          : []),
        '',
        `Applying all ${out.opportunities.length} rows removes **${kb(total)}** of ${kb(out.eagerRaw)} eager JS (${((total / out.eagerRaw) * 100).toFixed(1)}%).`,
        'A row that scores far below its package size is blocked, not cheap: the libraries listed in the',
        'fix list below still hold the package eager, and the simulation already accounts for them.',
        ...(barrelSplits.length ? ['The `estimate` rows above are additional and are not folded into this before/after summary.'] : []),
        '',
      );
    }

    if (out.blockedFromAppCode?.length) {
      const blockedTotal = out.blockedFromAppCode.reduce((sum, b) => sum + b.eagerBytes, 0);
      lines.push(
        '### What no app-side edit can free',
        '',
        `${kb(blockedTotal)} of the eager set stays put whatever this repo does — cutting **every** app`,
        'import of these packages frees less than 20 KB each, because library-to-library edges keep them',
        'reachable. These are upstream work (split the barrel, or defer the library that pulls them in),',
        'not candidates for this MR.',
        '',
        '| Package | Eager | App files importing it | Freed if all those imports were cut |',
        '| --- | ---: | ---: | ---: |',
      );
      for (const b of out.blockedFromAppCode) {
        lines.push(`| \`${b.name}\` | ${kb(b.eagerBytes)} | ${b.appEdges} | ${kb(b.freedIfAllAppEdgesCut)} |`);
      }
      lines.push('');
    }
  } else {
    lines.push('> No ranked plan: the metafile was not available, so nothing could be simulated. Pass `--dist` or `--stats`.', '');
  }
  lines.push('| Repository | Eager | % of eager | Packages in the eager set | Upstream findings |', '| --- | ---: | ---: | --- | ---: |');
  for (const r of out.repos) {
    if (!r.eagerRaw) continue;
    const label = r.remote ? `\`${r.remote}\`` : `\`${r.repo}\``;
    lines.push(`| ${label} | ${kb(r.eagerRaw)} | ${r.shareOfEagerPct}% | ${r.packages.map((p) => `\`${p}\``).join(', ') || '—'} | ${r.upstreamFindings} |`);
  }
  lines.push('');

  const eager = out.libraries.filter((l) => l.eagerRaw > 0).sort((a, b) => b.eagerRaw - a.eagerRaw);
  if (eager.length) {
    lines.push('## Internal libraries in the eager set', '');
    lines.push(
      '| Package | Eager | % | `sideEffects` | Subpaths | NgModules | Shakes? | Fix belongs to |',
      '| --- | ---: | ---: | --- | ---: | ---: | --- | --- |',
    );
    for (const l of eager) {
      const p = l.packaging;
      lines.push(
        `| \`${l.name}\` | ${kb(l.eagerRaw)} | ${l.shareOfEagerPct}% | ${p ? String(p.sideEffects) : '?'} | ${p?.subpathExports ?? '?'} | ${p?.ngModuleCount ?? '?'} | ${shakeCell(p?.shake)} | **${l.diagnosis.owner}** |`,
      );
    }
    lines.push('');

    lines.push('### Why', '');
    for (const l of eager) {
      lines.push(`- \`${l.name}\` (${kb(l.eagerRaw)}, ${l.diagnosis.owner})${l.repoRemote ? ` — owned by \`${l.repoRemote}\`` : ''}`);
      for (const reason of l.diagnosis.reasons) lines.push(`  - ${reason}`);
    }
    lines.push('');
  }

  const withFixes = eager.filter((l) => l.fixes.length);
  if (withFixes.length) {
    lines.push(
      '## How to fix each owned dependency',
      '',
      'One block per owned package holding at least 20 KB of the eager set, largest first —',
      'anything smaller is listed in the tables above without a block, because a fix for 3 KB costs',
      'more attention than the bytes are worth. Each item says what to change, where (the real',
      'importers, read off the metafile), why it costs bytes, and the command that proves it landed.',
      '`upstream` items are an MR on the owning repo, not this one; `consumer` items are this repo.',
      '',
    );
    for (const l of withFixes) {
      lines.push(
        `### \`${l.name}\` — ${kb(l.eagerRaw)} eager (${l.shareOfEagerPct}% of first load)${l.repoRemote ? `, owned by \`${l.repoRemote}\`` : ''}`,
        '',
      );
      l.fixes.forEach((f, i) => {
        lines.push(`${i + 1}. **${f.what}** — _${f.tier}_`);
        lines.push(`   - Where: ${f.where}`);
        lines.push(`   - Why it costs: ${f.why}`);
        lines.push(`   - How: ${f.how}`);
        lines.push(`   - Proof: ${f.verify}`);
      });
      lines.push('');
    }
    lines.push(
      'Sizes above are the bytes the package occupies **today**. None of them is a predicted saving:',
      'a fix is worth what the next metafile says it is worth, and packaging fixes in particular shrink',
      'what ships without changing *when* it loads.',
      '',
    );
  }

  if (out.thirdPartyOwners.length) {
    lines.push('## Third-party packages we do not own — context only', '');
    lines.push(
      'No packaging verdict is given for these and none should be raised: we cannot set `sideEffects`',
      "or split entry points in someone else's package, and forking one to move a number is not a fix.",
      'The only lever is *when* they load, which is decided by the importer named in the last column.',
      '',
    );
    lines.push('| Package | Eager | App declares it? | Required by our libraries | Lever |', '| --- | ---: | :---: | --- | --- |');
    for (const t of out.thirdPartyOwners) {
      lines.push(
        `| \`${t.name}\` | ${kb(t.raw)} | ${t.declaredByApp ? 'yes' : 'no'} | ${t.requiredByInternalLibs.map((l) => `\`${l}\``).join(', ') || '—'} | ${lever(t)} |`,
      );
    }
    lines.push(
      '',
      'A package required by an internal library cannot be dropped by the app alone, however it is imported locally — while that library sits in the eager graph the dependency comes with it. Those rows are cross-repo work, not app refactors.',
      '',
    );
  }

  const unresolved = out.libraries.filter((l) => l.eagerRaw > 0 && !l.repo).map((l) => l.name);
  if (unresolved.length) {
    lines.push(
      `> Source repo not found locally for ${unresolved.map((n) => `\`${n}\``).join(', ')} — clone it under \`${out.reposRoot}\` (or pass \`--repos-root\`) to attribute those bytes to a repo.`,
      '',
    );
  }
  return lines.join('\n');
}

/**
 * What can actually be done about a package we do not own. Never "repackage it" —
 * the choice is between deferring our own importer and dropping the dependency,
 * and which one applies is decided by who requires it.
 */
function lever(t) {
  if (t.requiredByInternalLibs.length) {
    return `defer ${t.requiredByInternalLibs.map((l) => `\`${l}\``).join(', ')} first — it comes with them${t.declaredByApp ? ", and drop the app's own import after" : ''}`;
  }
  if (t.declaredByApp) return 'defer or dynamically `import()` the app code that uses it, or replace it with a lighter equivalent';
  return 'transitive — find the eager importer with `--trace` before planning anything';
}

function writeJson(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function writeText(path, text) {
  writeFileSync(path, text);
}

/**
 * Every module inside the eager set that imports `target`, split into app code and
 * other libraries.
 *
 * This exists because of a candidate that looked certain and moved nothing.
 * `@design-system/atoms` was 138 KB of the eager set and the only *app* files importing
 * it were two conditional shell components, so deferring both looked like it would
 * drop the whole chunk. It dropped 6 KB: `@design-system/molecules`, `organisms`,
 * `templates` and four `@web-shared` packages import atoms too, and all of them were
 * still eager. A chunk leaves the eager set only when its LAST eager importer does.
 *
 * Scanning app code alone will therefore overstate a saving by any amount. Trace
 * before deferring, and treat library-to-library edges as first-class.
 */
function traceImporters(metafile, target, distDir) {
  const { app, libs } = importersOf(metafile, target, eagerOutputs(metafile, distDir));

  const lines = [`# Eager importers of \`${target}\``, ''];
  lines.push(`App code (${app.length}):`, ...(app.length ? app.map((f) => `- ${f}`) : ['- none']), '');
  lines.push(`Other libraries (${libs.length}):`, ...(libs.length ? [...new Set(libs)].map((f) => `- ${f}`) : ['- none']), '');
  lines.push(
    libs.length
      ? `**Deferring the app-code importers alone will NOT remove \`${target}\` from the eager set** — ${libs.length} library module(s) still reach it eagerly. Every one of them has to leave first, so pick a candidate that covers them or choose a different package.`
      : `No library reaches \`${target}\` eagerly, so deferring the app-code importers above should remove it. Prove it with a re-measure.`,
    '',
  );
  return lines.join('\n');
}

/**
 * Every module in the eager set that imports `target`, split into app code and
 * other libraries. Shared by `--trace` and by the fix list, so the report and the
 * trace can never disagree about who holds a package eager.
 */
function importersOf(metafile, target, eager) {
  const modules = new Set();
  for (const name of eager) for (const input of Object.keys(metafile.outputs[name]?.inputs ?? {})) modules.add(input);

  const app = [];
  const libs = new Set();
  for (const file of modules) {
    const info = metafile.inputs[file];
    if (!info) continue;
    if (!(info.imports ?? []).some((i) => (i.original ?? i.path ?? '').includes(target))) continue;
    const label = file.replace(/^.*node_modules\/(\.pnpm\/[^/]+\/node_modules\/)?/, '');
    if (file.startsWith('src/')) app.push(label);
    else if (!label.startsWith(`${target}/`)) libs.add(label);
  }
  return { app, libs: [...libs] };
}

/** The eager output set, seeded from the initial scripts in the generated index HTML. */
function eagerOutputs(metafile, distDir) {
  const base = (p) => p.split('/').pop();
  const byBase = new Map(Object.keys(metafile.outputs).map((n) => [base(n), n]));
  let entries = [];
  for (const dir of [join(distDir, 'browser'), distDir]) {
    for (const file of ['index.csr.html', 'index.html']) {
      const path = join(dir, file);
      if (!existsSync(path)) continue;
      const html = readFileSync(path, 'utf8');
      const refs = new Set();
      for (const m of html.matchAll(/(?:src|href)="([^"]+\.js)"/g)) refs.add(base(m[1]));
      entries = [...refs].map((f) => byBase.get(f)).filter(Boolean);
      if (entries.length) break;
    }
    if (entries.length) break;
  }
  if (!entries.length) {
    entries = Object.keys(metafile.outputs).filter((n) => /(^|\/)(src\/)?main\.ts$/.test(metafile.outputs[n].entryPoint ?? ''));
  }

  const eager = new Set();
  const queue = [...entries];
  while (queue.length) {
    const name = queue.pop();
    if (eager.has(name)) continue;
    eager.add(name);
    for (const imp of metafile.outputs[name]?.imports ?? []) {
      if (imp.kind === 'dynamic-import') continue;
      if (metafile.outputs[imp.path]) queue.push(imp.path);
    }
  }
  return eager;
}

function findStats(dist) {
  for (const candidate of [join(dist, 'browser', 'stats.json'), join(dist, 'stats.json')]) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

function expandHome(p) {
  return p.startsWith('~') ? join(homedir(), p.slice(1)) : p;
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith('--')) continue;
    out[argv[i].slice(2)] = argv[i + 1]?.startsWith('--') ? true : argv[++i];
  }
  return out;
}

function fail(message) {
  process.stderr.write(`analyze-deps: ${message}\n`);
  process.exit(1);
}
