#!/usr/bin/env node
/**
 * compare-bundle.mjs — diff two `analyze-bundle.mjs` reports and print the
 * reduction table that goes into the MR description and the OKR.
 *
 * Output: the before/after table, the packages that moved, a **verdict** that
 * separates a real first-load saving from bytes merely relocated out of `main`,
 * the gap to a stated goal, and the ranked list of what is still worth doing.
 *
 * Usage:
 *   node compare-bundle.mjs --baseline baseline.json --current bundle-report.json \
 *        [--md delta.md] [--goal 15] [--min-reduction 15] [--metric main|eager-gzip|eager-raw]
 *
 * --goal reports the remaining distance to the target (never gates).
 * --min-reduction gates: exit 2 when the chosen metric improved by less than N
 * percent, so a pipeline stage can enforce it.
 *
 * Exit codes: 0 target met (or no target set), 1 usage/IO error, 2 target missed.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';

const args = parseArgs(process.argv.slice(2));
if (!args.baseline || !args.current) {
  fail('usage: compare-bundle.mjs --baseline <baseline.json> --current <report.json> [--md <out.md>] [--min-reduction <pct>] [--metric main|eager-gzip|eager-raw]');
}
for (const p of [args.baseline, args.current]) if (!existsSync(p)) fail(`report not found: ${p}`);

const before = JSON.parse(readFileSync(args.baseline, 'utf8'));
const after = JSON.parse(readFileSync(args.current, 'utf8'));

const rows = [
  row('main chunk (raw)', before.main?.raw, after.main?.raw),
  row('main chunk (gzip)', before.main?.gzip, after.main?.gzip),
  row('eager JS (raw)', before.eager?.raw, after.eager?.raw),
  row('eager JS (gzip)', before.eager?.gzip, after.eager?.gzip),
  row('total JS emitted (raw)', before.totalJsRaw, after.totalJsRaw),
].filter(Boolean);

const movers = packageDeltas(before, after);
const goal = args.goal !== undefined ? Number(args.goal) : undefined;
const md = renderMarkdown(rows, movers, verdict(rows, movers), after.opportunities ?? [], goal ? gapToGoal(rows, goal, args.metric ?? 'eager-gzip') : null);
if (args.md) writeFileSync(args.md, md);
process.stdout.write(md);

if (args['min-reduction'] !== undefined) {
  const metric = args.metric ?? 'main';
  const label = { main: 'main chunk (raw)', 'eager-gzip': 'eager JS (gzip)', 'eager-raw': 'eager JS (raw)' }[metric];
  if (!label) fail(`unknown --metric ${metric} (expected main | eager-gzip | eager-raw)`);
  const target = Number(args['min-reduction']);
  const observed = rows.find((r) => r.label === label);
  if (!observed) fail(`metric "${label}" missing from one of the reports`);
  if (observed.pct < target) {
    process.stderr.write(`\ncompare-bundle: ${label} reduced ${observed.pct.toFixed(1)}%, target was ${target}%\n`);
    process.exit(2);
  }
  process.stdout.write(`\ncompare-bundle: ${label} reduced ${observed.pct.toFixed(1)}% (target ${target}%) — PASS\n`);
}

// ---------------------------------------------------------------------------

function row(label, beforeBytes, afterBytes) {
  if (typeof beforeBytes !== 'number' || typeof afterBytes !== 'number') return null;
  const delta = afterBytes - beforeBytes;
  const pct = beforeBytes === 0 ? 0 : (-delta / beforeBytes) * 100;
  return { label, before: beforeBytes, after: afterBytes, delta, pct };
}

/** Packages that moved the most between the two eager sets, biggest saving first. */
function packageDeltas(beforeReport, afterReport) {
  const b = new Map((beforeReport.packages ?? []).map((p) => [p.name, p.raw]));
  const a = new Map((afterReport.packages ?? []).map((p) => [p.name, p.raw]));
  const names = new Set([...b.keys(), ...a.keys()]);
  return [...names]
    .map((name) => ({ name, before: b.get(name) ?? 0, after: a.get(name) ?? 0 }))
    .map((p) => ({ ...p, delta: p.after - p.before }))
    .filter((p) => Math.abs(p.delta) >= 1024)
    .sort((x, y) => x.delta - y.delta)
    .slice(0, 15);
}

/**
 * Read the two numbers honestly. The failure mode this exists to catch: `main`
 * drops a lot while the eager total barely moves, which means code was relocated
 * into an eagerly-imported chunk and the user waits exactly as long as before.
 */
function verdict(rows, movers) {
  const pct = (label) => rows.find((r) => r.label === label)?.pct ?? 0;
  const mainPct = pct('main chunk (raw)');
  const eagerPct = pct('eager JS (raw)');
  const notes = [];

  if (mainPct >= 5 && eagerPct < 1) {
    notes.push(
      `**Relocation, not a reduction.** \`main\` fell ${mainPct.toFixed(1)}% but the eager set moved ${eagerPct.toFixed(1)}% — the bytes went into another eagerly-imported chunk. First load is unchanged. Do not report this as a saving.`,
    );
  } else if (eagerPct >= 1) {
    notes.push(
      `Eager set down ${eagerPct.toFixed(1)}% raw — a real first-load saving. \`main\` moved ${mainPct.toFixed(1)}%; report both, headline whichever metric the stakeholder named.`,
    );
  } else if (eagerPct <= -1) {
    notes.push(`**Regression:** the eager set grew ${Math.abs(eagerPct).toFixed(1)}%. Revert the candidate before continuing.`);
  } else {
    notes.push('No material movement in the eager set. Treat the candidate as failed and demote it to the REPORT tier.');
  }

  const left = movers.filter((m) => m.after === 0 && m.before > 0).map((m) => m.name);
  const shrank = movers.filter((m) => m.after > 0 && m.delta < 0).map((m) => m.name);
  if (left.length) notes.push(`Left the eager set entirely: ${left.map((n) => `\`${n}\``).join(', ')} — the intended outcome.`);
  if (shrank.length) {
    notes.push(
      `Only shrank, still eager: ${shrank.map((n) => `\`${n}\``).join(', ')} — usually a partial change (one import path missed). Find the remaining eager importer before calling it done.`,
    );
  }
  return notes;
}

/** How far the current state is from a target stated against the baseline. */
function gapToGoal(rows, goalPct, metric) {
  const label = { main: 'main chunk (raw)', 'eager-gzip': 'eager JS (gzip)', 'eager-raw': 'eager JS (raw)' }[metric] ?? 'eager JS (gzip)';
  const r = rows.find((x) => x.label === label);
  if (!r) return null;
  const targetBytes = r.before * (1 - goalPct / 100);
  return { label, goalPct, achievedPct: r.pct, targetBytes, remainingBytes: Math.max(0, r.after - targetBytes) };
}

function renderMarkdown(rows, movers, notes, remaining, gap) {
  const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
  const signed = (n) => `${n > 0 ? '+' : ''}${kb(n)}`;
  const lines = ['# Bundle delta', '', '| Metric | Before | After | Delta | Reduction |', '| --- | ---: | ---: | ---: | ---: |'];
  for (const r of rows) lines.push(`| ${r.label} | ${kb(r.before)} | ${kb(r.after)} | ${signed(r.delta)} | **${r.pct.toFixed(1)}%** |`);
  if (movers.length) {
    lines.push('', '## Packages that moved in the eager set', '', '| Package | Before | After | Delta |', '| --- | ---: | ---: | ---: |');
    for (const m of movers) lines.push(`| \`${m.name}\` | ${kb(m.before)} | ${kb(m.after)} | ${signed(m.delta)} |`);
  }

  lines.push('', '## Verdict', '');
  for (const n of notes) lines.push(`- ${n}`);

  if (gap) {
    lines.push('', '## Against the goal', '');
    if (gap.achievedPct >= gap.goalPct) {
      lines.push(`- ${gap.label}: **${gap.achievedPct.toFixed(1)}% reduced, target ${gap.goalPct}% — MET.**`);
    } else {
      lines.push(
        `- ${gap.label}: ${gap.achievedPct.toFixed(1)}% reduced, target ${gap.goalPct}%. **${kb(gap.remainingBytes)} still to remove** (target is ${kb(gap.targetBytes)}).`,
      );
    }
  }

  if (remaining.length) {
    lines.push('', '## What to improve next (still eager, ranked)', '');
    lines.push('| Package | Raw | % of eager | Pattern | Why it is eager |', '| --- | ---: | ---: | --- | --- |');
    for (const o of remaining) lines.push(`| \`${o.name}\` | ${kb(o.raw)} | ${o.shareOfEagerPct}% | ${o.pattern ?? '—'} | ${o.note} |`);
    lines.push('', 'Estimates, for ranking only. Each one becomes its own candidate, its own commit, its own metafile proof.');
  } else {
    lines.push('', '_No ranked opportunities in the current report — regenerate it with an `analyze-bundle.mjs` of schema 2 or later._');
  }

  lines.push('');
  return lines.join('\n');
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
  process.stderr.write(`compare-bundle: ${message}\n`);
  process.exit(1);
}
