# PM2 and Deployment Configuration

Applies only if the project deploys its SSR server via PM2 (look for `ecosystem.*.config.js` files). If the project starts the server another way (plain `node`, a Docker `CMD`, systemd, etc.), apply the same principle — *verify the server entry point still matches the build output after the upgrade* — to whatever mechanism it uses.

## PM2 Configuration Files

A project typically has one PM2 ecosystem config per environment (e.g. `ecosystem.prod.config.js`, `ecosystem.stage.config.js`). Discover the actual set from the repo rather than assuming.

### Structure

Each config usually defines a main application and, optionally, a monitoring/sidecar process:

**1. Main Application** — runs the Angular SSR server build output:
```javascript
{
  name: '<app-name>',
  script: './dist/server/server.mjs',  // ESM output from the Angular build
  instances: 3,                         // deployment-specific (cluster mode)
  exec_mode: 'cluster',
  node_args: [
    '--max-old-space-size=1200',
    // ...heap snapshot / profiling flags, infra-specific
  ],
  env: { NODE_ENV: 'prod' },
  autorestart: true,
  min_uptime: '1m',
  max_restarts: 3,
}
```

**2. Monitoring Plugin (optional)** — e.g. a New Relic / APM sidecar:
```javascript
{
  name: '<plugin-name>',
  script: './<plugin>.config.js',
  instances: 1,
  exec_mode: 'fork',
}
```

The exact app name, instance count, `node_args`, and any heap-dump/diagnostic paths vary by project and environment — treat them as infrastructure, not framework concerns.

## What to Check During Angular Upgrades

### 1. Script Entry Point (the one that actually matters)

The main app's `script` field points at the SSR build output (commonly `./dist/server/server.mjs`). This path **must still resolve after the upgrade**.

If Angular changes the output directory structure (it has across majors):
- Check `angular.json` → `outputPath` and `outputMode`
- Confirm where the server bundle actually lands
- Verify after build: `ls -la dist/server/server.mjs` (adjust path to match the project)
- Update the PM2 `script` field if the location changed

### 2. ESM Compatibility

The entry point is typically `.mjs` (ESM). If Angular changes the emitted module format:
- Update the PM2 `script` path / extension accordingly
- Ensure `node_args` don't conflict with the new module format

### 3. Node.js Arguments

`node_args` (memory limit, heap snapshots, heap profiling) are Node.js flags, not Angular-specific. They should not change during an Angular upgrade unless the Node.js version requirement changes.

### 4. Monitoring Plugin

Any APM/monitoring sidecar config is unrelated to Angular and should NOT be modified during an Angular upgrade.

## What NOT to Change

- PM2 instance count (deployment-specific)
- Node.js memory limits and heap flags (tuned for production)
- Heap dump / diagnostic paths (infrastructure-specific)
- Monitoring plugin configuration
- Environment variables (deployment-specific)

## When PM2 Config DOES Need Changes

Only change PM2 configs if:
1. The Angular build output path changes → update the `script` field
2. The output format changes from ESM to something else → update the file extension
3. A new Node.js version is required that drops support for current flags
4. **Native Federation SSR (adapter v20+)**: the entry point is `fstart.mjs`, not `server.mjs` — the `script` field must point at `./dist/{project}/server/fstart.mjs` (it initializes federation, then delegates to `server.mjs`). Starting `server.mjs` directly skips federation init and remotes won't resolve server-side. See `references/native-federation.md`.
