#!/usr/bin/env node
/**
 * analyze-bundle.mjs — eager-bundle analyzer for Angular repos built with
 * `@angular/build` (esbuild). Consumes the esbuild metafile that
 * `ng build --stats-json` writes and answers the only question that matters
 * for first-load performance: *which bytes ship before the router lazy-loads
 * anything, and which npm package do they belong to?*
 *
 * Usage:
 *   node analyze-bundle.mjs [--stats <path>] [--out <path>] [--md <path>] [--top <n>]
 *
 * Defaults: --stats auto-discovered under dist/, --out bundle-report.json,
 *           --md bundle-report.md, --top 25
 *
 * Exit codes: 0 ok, 1 usage/IO error.
 */
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { join, dirname, basename } from 'node:path';

const args = parseArgs(process.argv.slice(2));

const statsPath = args.stats ?? discoverStats(args.dist ?? 'dist');
if (!statsPath) {
  fail(
    'No stats.json found. Run the build with --stats-json first, e.g.\n' +
      '  ng build --configuration=production --stats-json\n' +
      'then re-run with --stats <path>.',
  );
}
if (!existsSync(statsPath)) fail(`stats file not found: ${statsPath}`);

const metafile = JSON.parse(readFileSync(statsPath, 'utf8'));
if (!metafile.outputs || !metafile.inputs) {
  fail(
    `${statsPath} is not an esbuild metafile (no "inputs"/"outputs" keys).\n` +
      'Webpack-builder repos are not supported by this script — see references/detection.md.',
  );
}

// The emitted files are not necessarily next to stats.json — Angular writes
// stats.json to dist/ while the browser assets live in dist/browser/.
const assetDir = discoverAssetDir(args.dist ?? dirname(statsPath));
const report = analyze(metafile, assetDir);

writeFileSync(args.out ?? 'bundle-report.json', JSON.stringify(report, null, 2));
const md = renderMarkdown(report, Number(args.top ?? 25));
writeFileSync(args.md ?? 'bundle-report.md', md);
process.stdout.write(md);

// ---------------------------------------------------------------------------

/**
 * Walk the static-import graph from every initial entry point. An output chunk
 * is *eager* when it is reachable without crossing a `dynamic-import` edge —
 * that is exactly the set the browser must download before it can render.
 */
function analyze(metafile, outDir) {
  const outputs = metafile.outputs;

  const entries = initialEntries(outputs, outDir);
  if (!entries.length) {
    fail(
      'Could not determine the initial entry points.\n' +
        `Looked for index.html / index.csr.html in ${outDir} and for a "src/main.ts" entryPoint in the metafile.\n` +
        'Pass --dist <dir> pointing at the browser output directory.',
    );
  }

  const eager = new Set();
  const queue = [...entries];
  while (queue.length) {
    const name = queue.pop();
    if (eager.has(name)) continue;
    eager.add(name);
    for (const imp of outputs[name]?.imports ?? []) {
      if (imp.kind === 'dynamic-import') continue;
      if (!outputs[imp.path]) continue;
      queue.push(imp.path);
    }
  }

  const chunks = [];
  const packages = new Map();
  let eagerRaw = 0;
  let eagerGzip = 0;
  let totalJsRaw = 0;

  for (const [name, out] of Object.entries(outputs)) {
    if (!name.endsWith('.js')) continue;
    totalJsRaw += out.bytes;
    if (!eager.has(name)) continue;

    const gzip = gzipOf(join(outDir, basename(name)), out.bytes);
    eagerRaw += out.bytes;
    eagerGzip += gzip;

    const contributors = [];
    for (const [input, meta] of Object.entries(out.inputs ?? {})) {
      const bytes = meta.bytesInOutput ?? 0;
      if (bytes <= 0) continue;
      const pkg = packageOf(input);
      packages.set(pkg, (packages.get(pkg) ?? 0) + bytes);
      contributors.push({ package: pkg, input, bytes });
    }
    contributors.sort((a, b) => b.bytes - a.bytes);

    chunks.push({
      name: basename(name),
      isEntry: entries.includes(name),
      raw: out.bytes,
      gzip,
      topContributors: contributors.slice(0, 5),
    });
  }

  chunks.sort((a, b) => b.raw - a.raw);

  // Only the stylesheets the index HTML links. Component styles for lazy routes
  // are emitted as .css outputs too and are not part of first load.
  const initialCss = initialStylesheets(outputs, outDir);
  const styles = initialCss
    .map((name) => ({
      name: basename(name),
      raw: outputs[name].bytes,
      gzip: gzipOf(join(outDir, basename(name)), outputs[name].bytes),
    }))
    .sort((a, b) => b.raw - a.raw);

  const mainChunk = chunks.find((c) => c.isEntry && /^main[.-]/.test(c.name)) ?? null;

  const packageList = [...packages.entries()].map(([name, raw]) => ({ name, raw })).sort((a, b) => b.raw - a.raw);

  // Angular's `initial` budget counts eager JS *and* the initial stylesheets, in
  // raw bytes. Computing it here removes the trap of ratcheting the budget to the
  // eager-JS number alone, which sets it below what the build actually emits.
  const initialCssRaw = styles.reduce((sum, s) => sum + s.raw, 0);
  const initialRaw = eagerRaw + initialCssRaw;

  return {
    schema: 2,
    statsPath,
    eager: { raw: eagerRaw, gzip: eagerGzip, chunkCount: chunks.length },
    initialBudget: {
      raw: initialRaw,
      cssRaw: initialCssRaw,
      suggestedWarningKb: Math.ceil((initialRaw * 1.03) / 1024),
      suggestedErrorKb: Math.ceil((initialRaw * 1.08) / 1024),
    },
    main: mainChunk ? { name: mainChunk.name, raw: mainChunk.raw, gzip: mainChunk.gzip } : null,
    totalJsRaw,
    chunks,
    styles,
    // Full list, not truncated: compare-bundle.mjs diffs these across runs and
    // a package that drops out of the eager set entirely must still be visible.
    packages: packageList,
    // What is still worth attacking, ranked. Carried in the JSON so
    // compare-bundle.mjs can print "what to do next" without re-classifying.
    opportunities: opportunities(packageList, eagerRaw),
  };
}

/**
 * Map an eager package to a playbook pattern. Deliberately coarse: this ranks
 * candidates for a human to choose from, it never claims a saving. `irreducible`
 * marks the framework floor — reporting @angular/core as an "opportunity" wastes
 * the reader's attention.
 */
// A function, not a `const` array: the analysis runs at the top of this module,
// above these declarations, and a `const` would still be in its temporal dead zone.
function patterns() {
  return [
    { re: /^(@angular\/core|@angular\/common|@angular\/platform-browser|@angular\/router|@angular\/forms|rxjs|zone\.js|tslib)$/, pattern: null, irreducible: true, note: 'framework floor — not reducible' },
    { re: /^(swiper|lottie-web|@lottiefiles\/|@stencil\/|hammerjs|chart\.js)/, pattern: 'P1', note: 'side-effect register/import at bootstrap — move into the consuming components' },
    { re: /^@angular\/(material|cdk)/, pattern: 'P5', note: 'entry-point hygiene — import only the used `@angular/material/*` subpaths; push dialog-heavy flows into lazy routes' },
    { re: /^(crypto-js|moment|moment-timezone|lodash|date-fns|ua-parser-js)$/, pattern: 'P6', note: 'heavy utility eager via a transitive dep — `pnpm why`, then lazy-load or swap for a platform API' },
    { re: /^@design-system\//, pattern: 'P4', note: 'design-system UI pulled in by the always-on shell — `@defer (on viewport|on interaction)`' },
    { re: /^@angular\/animations$/, pattern: 'P2', note: 'eager provider in the app config — check `provideAnimations` vs `provideAnimationsAsync`' },
    { re: /^(@web-shared\/|@your-org\/)/, pattern: 'P3', note: 'feature internals reached statically from the root routes file — import types only, load the rest inside the route' },
    { re: /^src \(app code\)$/, pattern: 'P3', note: 'app code in the eager set — usually guards/resolvers/services imported at the top of root-routes.ts' },
  ];
}

function classify(name) {
  for (const p of patterns()) if (p.re.test(name)) return p;
  return { pattern: null, irreducible: false, note: 'no pattern matched — inspect the importing chunk before acting' };
}

function opportunities(packageList, eagerRaw) {
  return packageList
    .map((p) => ({ ...p, ...classify(p.name) }))
    .filter((p) => !p.irreducible && p.raw >= 20 * 1024)
    .slice(0, 12)
    .map(({ name, raw, pattern, note }) => ({
      name,
      raw,
      shareOfEagerPct: eagerRaw ? Number(((raw / eagerRaw) * 100).toFixed(1)) : 0,
      pattern,
      note,
    }));
}

/**
 * The initial scripts, taken from the generated index HTML — the browser's own
 * definition of "what loads first".
 *
 * `entryPoint` cannot be used for this. Angular's esbuild build emits one entry
 * per lazily-loaded component, so almost every chunk in the metafile carries an
 * `entryPoint` and treating that as "initial" marks the whole app eager.
 */
function initialEntries(outputs, outDir) {
  const byBasename = new Map();
  for (const name of Object.keys(outputs)) byBasename.set(basename(name), name);

  const html = readIndexHtml(outDir);
  if (html) {
    const refs = new Set();
    for (const m of html.matchAll(/<script[^>]+src="([^"]+)"/g)) refs.add(basename(m[1]));
    for (const m of html.matchAll(/rel="modulepreload"[^>]+href="([^"]+)"/g)) refs.add(basename(m[1]));
    for (const m of html.matchAll(/href="([^"]+)"[^>]+rel="modulepreload"/g)) refs.add(basename(m[1]));

    const resolved = [...refs]
      .filter((f) => f.endsWith('.js'))
      .map((f) => byBasename.get(f))
      .filter(Boolean);
    if (resolved.length) return resolved;
  }

  // Fallback for builds with no index HTML on disk (library or SSR-only output):
  // the application entry itself, which is always src/main.ts in an Angular app.
  return Object.keys(outputs).filter(
    (name) => name.endsWith('.js') && /(^|\/)(src\/)?main(\.server)?\.ts$/.test(outputs[name].entryPoint ?? ''),
  );
}

function initialStylesheets(outputs, outDir) {
  const byBasename = new Map();
  for (const name of Object.keys(outputs)) if (name.endsWith('.css')) byBasename.set(basename(name), name);

  const html = readIndexHtml(outDir);
  if (!html) return [];

  const refs = new Set();
  for (const m of html.matchAll(/<link[^>]+href="([^"]+\.css)"/g)) refs.add(basename(m[1]));
  return [...refs].map((f) => byBasename.get(f)).filter(Boolean);
}

function readIndexHtml(outDir) {
  for (const candidate of ['index.csr.html', 'index.html']) {
    const path = join(outDir, candidate);
    if (existsSync(path)) return readFileSync(path, 'utf8');
  }
  return null;
}

/** Where the emitted assets actually live — dist/browser/ on SSR builds, dist/ otherwise. */
function discoverAssetDir(start) {
  for (const candidate of [join(start, 'browser'), start]) {
    if (existsSync(join(candidate, 'index.csr.html')) || existsSync(join(candidate, 'index.html'))) return candidate;
  }
  return existsSync(join(start, 'browser')) ? join(start, 'browser') : start;
}

/** `node_modules/swiper/element/bundle.mjs` -> `swiper`; scoped names kept whole. */
function packageOf(input) {
  const idx = input.lastIndexOf('node_modules/');
  if (idx === -1) return 'src (app code)';
  const rest = input.slice(idx + 'node_modules/'.length).split('/');
  return rest[0].startsWith('@') ? `${rest[0]}/${rest[1]}` : rest[0];
}

/** Real gzip when the emitted file is on disk; otherwise a conservative estimate. */
function gzipOf(path, rawBytes) {
  try {
    if (existsSync(path) && statSync(path).isFile()) return gzipSync(readFileSync(path)).length;
  } catch {
    /* fall through to the estimate */
  }
  return Math.round(rawBytes * 0.29);
}

function renderMarkdown(r, top) {
  const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
  const lines = [];
  lines.push('# Bundle report', '');
  lines.push(`Source: \`${r.statsPath}\``, '');
  lines.push('| Metric | Raw | Gzip |', '| --- | ---: | ---: |');
  lines.push(`| Eager JS (${r.eager.chunkCount} chunks) | ${kb(r.eager.raw)} | ${kb(r.eager.gzip)} |`);
  if (r.main) lines.push(`| \`${r.main.name}\` | ${kb(r.main.raw)} | ${kb(r.main.gzip)} |`);
  for (const s of r.styles.slice(0, 3)) lines.push(`| \`${s.name}\` | ${kb(s.raw)} | ${kb(s.gzip)} |`);
  lines.push(`| Total JS emitted (eager + lazy) | ${kb(r.totalJsRaw)} | — |`);
  lines.push('');
  if (r.initialBudget) {
    lines.push(
      `Angular \`initial\` budget basis: **${kb(r.initialBudget.raw)}** raw ` +
        `(eager JS ${kb(r.eager.raw)} + initial CSS ${kb(r.initialBudget.cssRaw)}). ` +
        `Ratchet to \`maximumWarning: "${r.initialBudget.suggestedWarningKb}kb"\`, ` +
        `\`maximumError: "${r.initialBudget.suggestedErrorKb}kb"\`.`,
      '',
    );
  }

  lines.push(`## Top ${top} packages in the eager set`, '');
  lines.push('| Package | Raw |', '| --- | ---: |');
  for (const p of r.packages.slice(0, top)) lines.push(`| \`${p.name}\` | ${kb(p.raw)} |`);
  lines.push('');

  if (r.opportunities?.length) {
    lines.push('## Reduction opportunities (ranked, estimates only)', '');
    lines.push('| Package | Raw | % of eager | Pattern | Why it is eager |', '| --- | ---: | ---: | --- | --- |');
    for (const o of r.opportunities) {
      lines.push(`| \`${o.name}\` | ${kb(o.raw)} | ${o.shareOfEagerPct}% | ${o.pattern ?? '—'} | ${o.note} |`);
    }
    lines.push('', 'Framework packages (`@angular/core`, `rxjs`, `zone.js`, …) are excluded — they are the floor.', '');
  }

  lines.push('## Eager chunks', '');
  lines.push('| Chunk | Raw | Gzip | Top contributors |', '| --- | ---: | ---: | --- |');
  for (const c of r.chunks.slice(0, 15)) {
    const top3 = c.topContributors
      .slice(0, 3)
      .map((t) => `${t.package} ${kb(t.bytes)}`)
      .join(', ');
    lines.push(`| \`${c.name}\`${c.isEntry ? ' *(entry)*' : ''} | ${kb(c.raw)} | ${kb(c.gzip)} | ${top3} |`);
  }
  lines.push('');
  return lines.join('\n');
}

function discoverStats(dist) {
  for (const candidate of [join(dist, 'browser', 'stats.json'), join(dist, 'stats.json')]) {
    if (existsSync(candidate)) return candidate;
  }
  if (!existsSync(dist)) return null;
  for (const entry of readdirSync(dist, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const nested = join(dist, entry.name, 'stats.json');
    if (existsSync(nested)) return nested;
  }
  return null;
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
  process.stderr.write(`analyze-bundle: ${message}\n`);
  process.exit(1);
}
