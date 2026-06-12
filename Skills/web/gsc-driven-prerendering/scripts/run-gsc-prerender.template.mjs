#!/usr/bin/env node
/**
 * Fetches top pages from Google Search Console (one API call per path), sorts by
 * clicks descending, truncates to MAX_PRERENDER limits per path, and writes a
 * generated TypeScript constants file consumed by the Angular SSR config.
 *
 * Usage: npm run gsc-prerender   (or: node scripts/run-gsc-prerender.mjs)
 * Requires: Service account key file at $GSC_KEY_DIR/gsc-service-account.json
 *           with read access to the GSC property.
 *
 * Adjust the four marked sections below for your project:
 *   1. GSC_SITE_URL       — the verified GSC property
 *   2. OUTPUT_FILE        — where the generated .ts file should land
 *   3. MAX_PRERENDER      — per-path click-based budget
 *   4. PATH_QUERIES       — one entry per dynamic Angular route to prerender
 */

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { writeFileSync, mkdirSync } from 'node:fs';
import { google } from 'googleapis';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');

// 1. Verified GSC property (must match the protocol/host registered in GSC).
const GSC_SITE_URL = 'https://www.example.com';

// 2. Generated file location — keep it under src/app and reference it from
//    app.routes.server.ts. Mark it as generated so reviewers don't hand-edit.
const OUTPUT_FILE = join(projectRoot, 'src', 'app', 'prerender-routes', 'gsc-prerender-params.constant.ts');

// GSC max rows per query. Leave at the API ceiling — we sort/truncate locally.
const ROW_LIMIT_PER_PATH = 10000;

const GSC_KEY_DIR = process.env.GSC_KEY_DIR; // CI provides this; export it for local runs.
if (!GSC_KEY_DIR) {
  console.error(
    'Error: GSC_KEY_DIR environment variable is not set.\n' +
    'Export it before running: export GSC_KEY_DIR=/path/to/dir-containing/gsc-service-account.json\n' +
    'See references/service-account-setup.md for full setup instructions.'
  );
  process.exit(1);
}
const GSC_KEY_FILE = join(GSC_KEY_DIR, 'gsc-service-account.json');

// 3. Per-path click budget. Increase carefully — each prerendered route adds
//    headless-browser time to the build.
const MAX_PRERENDER = {
  // example: articles: 10,
};

// 4. One entry per Angular dynamic route you want GSC-driven params for.
//
//    - regex      : RE2-compatible (no lookahead/lookbehind). Sent to GSC API
//                   as `includingRegex`. Anchor with ^ and match a single path
//                   segment via [^/]+ to keep results scoped.
//    - paramKey   : matches the :param name in the Angular route definition.
//    - prefix     : pathname prefix used to strip the URL down to the param.
//    - limit      : top-N by clicks to keep.
//    - filterRow  : optional post-filter when regex alone can't exclude rows
//                   (RE2 has no lookahead). Returns true to keep the row.
const PATH_QUERIES = [
  // Example — copy and adapt:
  // {
  //   name: 'articles',
  //   regex: '^https://www\\.example\\.com/articles/[^/]+',
  //   paramKey: 'slug',
  //   prefix: '/articles/',
  //   limit: MAX_PRERENDER.articles,
  // },
];

async function main() {
  if (PATH_QUERIES.length === 0) {
    console.warn(
      'Warning: PATH_QUERIES is empty — no routes configured yet.\n' +
      'Add at least one entry before running. See references/path-query-recipe.md.'
    );
    process.exit(0);
  }

  let searchconsole;
  try {
    searchconsole = await getSearchConsoleClient();
  } catch (err) {
    console.error('Failed to create Search Console client. Place service account key at', GSC_KEY_FILE);
    throw err;
  }

  const { start, end } = getDateRange();
  const params = {};

  for (const query of PATH_QUERIES) {
    params[query.name] = await searchAnalytics(searchconsole, GSC_SITE_URL, { start, end }, query);
  }

  const outPath = writeGeneratedFile(params);
  console.log('Wrote', outPath);
  console.log(JSON.stringify(params, null, 2));
}

/** Create Search Console client using a service account key (JWT signing handled by googleapis). */
async function getSearchConsoleClient() {
  const auth = new google.auth.GoogleAuth({
    keyFile: GSC_KEY_FILE,
    scopes: ['https://www.googleapis.com/auth/webmasters.readonly'],
  });
  const authClient = await auth.getClient();
  return google.searchconsole({ version: 'v1', auth: authClient });
}

/** Returns GSC query date range: last 30 days to today, as YYYY-MM-DD. */
function getDateRange() {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 1);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

/** One GSC call per path; sort by clicks desc; emit top `limit` unique params. */
async function searchAnalytics(searchconsole, siteUrl, { start, end }, { regex, paramKey, prefix, limit, filterRow }) {
  const res = await searchconsole.searchanalytics.query({
    siteUrl,
    requestBody: {
      startDate: start,
      endDate: end,
      dimensions: ['page'],
      dimensionFilterGroups: [{ filters: [{ dimension: 'page', operator: 'includingRegex', expression: regex }] }],
      rowLimit: ROW_LIMIT_PER_PATH,
    },
  });
  const rows = res.data?.rows ?? [];
  const filtered = filterRow ? rows.filter((row) => filterRow(row.keys?.[0])) : rows;
  const sorted = [...filtered].sort((a, b) => (b.clicks ?? 0) - (a.clicks ?? 0));

  const params = [];
  const seen = new Set();
  for (const row of sorted) {
    if (params.length >= limit) break;
    const value = extractParam(row.keys?.[0], prefix);
    if (value && !seen.has(value)) {
      seen.add(value);
      params.push({ [paramKey]: value });
    }
  }
  return params;
}

/** Extract param value from page URL (e.g. /articles/my-post -> my-post). Drops nested paths. */
function extractParam(pageUrl, prefix) {
  if (!pageUrl || typeof pageUrl !== 'string') return null;
  try {
    const path = new URL(pageUrl).pathname;
    if (!path.startsWith(prefix)) return null;
    const rest = path.slice(prefix.length).replace(/\/$/, '');
    return rest && !rest.includes('/') ? rest : null;
  } catch {
    return null;
  }
}

function writeGeneratedFile(params) {
  const entries = PATH_QUERIES.map((q) => {
    const list = (params[q.name] ?? [])
      .map((o) => `    { ${q.paramKey}: ${JSON.stringify(o[q.paramKey])} }`)
      .join(',\n');
    return `  ${q.name}: [\n${list}\n  ],`;
  }).join('\n');

  const ts = `// Generated by scripts/run-gsc-prerender.mjs - do not edit by hand.
// Run: npm run gsc-prerender

export const gscPrerenderParamsData = {
${entries}
};
`;
  mkdirSync(join(OUTPUT_FILE, '..'), { recursive: true });
  writeFileSync(OUTPUT_FILE, ts, 'utf8');
  return OUTPUT_FILE;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
