# SSR Migration Patterns

This reference covers Angular SSR-specific migration patterns for Angular projects that use SSR.

## Typical SSR Architecture

Common SSR projects typically use:
- **Builder**: `@angular/build:application` (not the legacy `@angular-devkit/build-angular:server`)
- **SSR entry**: `src/server.ts` (a custom Express 5 server)
- **Server bootstrap**: `src/main.server.ts`
- **Server config**: `src/app/app.config.server.ts`
- **Server routes**: `src/app/app.routes.server.ts`
- **Output mode**: `"server"` (full SSR, not static prerendering)
- **Output path**: `dist/server/server.mjs` (ESM output)

Confirm these against the target project's `angular.json` and `src/` layout before applying any pattern below.

## Critical SSR Files and Their Patterns

### 1. `src/server.ts` - Express Server

**Key imports from `@angular/ssr/node`:**
```typescript
import { AngularNodeAppEngine, createNodeRequestHandler, writeResponseToNodeResponse } from '@angular/ssr/node';
```

**AngularNodeAppEngine instantiation:**
```typescript
const angularApp = new AngularNodeAppEngine({
  allowedHosts: [new URL(environment.hostName).hostname],
});
```

**Request handling pattern:**
```typescript
const response = await angularApp.handle(req, requestContext);
// HTML responses get nonce injection
if (contentType.includes('text/html')) {
  const htmlText = await response.text();
  const updatedHtml = injectNonceIntoScripts(htmlText, nonce);
  res.send(updatedHtml);
} else {
  await writeResponseToNodeResponse(response, res);
}
```

**Export pattern (critical for SSR build):**
```typescript
export const reqHandler = createNodeRequestHandler(getOrCreateServer());
```

When upgrading, check if:
- `AngularNodeAppEngine` constructor API changed
- `handle()` method signature changed
- `createNodeRequestHandler` is still the correct export
- `writeResponseToNodeResponse` still exists

### 2. `src/app/app.config.server.ts` - Server Providers

**Current pattern:**
```typescript
import { provideServerRendering, withRoutes } from '@angular/ssr';

const serverConfig: ApplicationConfig = {
  providers: [
    provideServerRendering(withRoutes(serverRoutes)),
    importProvidersFrom(ServerModule, TranslateModule.forRoot({...})),
    { provide: HTTP_INTERCEPTORS, useClass: UniversalInterceptor, multi: true },
    { provide: XhrFactory, useClass: ServerXhr },
  ],
};
```

When upgrading, check if:
- `provideServerRendering` moved or was renamed
- `withRoutes` is still a valid feature for `provideServerRendering`
- `ServerModule` from `@angular/platform-server` is still needed or deprecated
- `XhrFactory` override pattern is still valid (xhr2 for server-side HTTP)

### 3. `angular.json` - Build Configuration

**Current SSR config (in staging/production/preprod):**
```json
{
  "server": "src/main.server.ts",
  "ssr": {
    "entry": "src/server.ts"
  },
  "outputMode": "server",
  "prerender": {
    "discoverRoutes": false
  },
  "externalDependencies": [
    "canvas",
    "zone.js/node"
  ]
}
```

When upgrading, check if:
- `outputMode` values changed
- `ssr.entry` format changed
- New SSR-related properties were added
- `externalDependencies` list needs updating

## What NOT to Touch During SSR Migration

These are business-specific implementations, NOT Angular SSR concerns:

1. **CSP Middleware** (`setSecurityHeaders` function) - Uses helmet for Content-Security-Policy with dynamic nonce generation. Only touch if helmet API changes.
2. **Nonce Injection** (`injectNonceIntoScripts` function) - Custom regex-based script tag nonce injection. Angular-independent.
3. **Redirect Routes** (in `server.ts`) - Business redirect logic. These use Express 5 route patterns (`/{*path}`, regex patterns). Only touch if Express route syntax changes.
4. **Prometheus Monitoring** (`setupPrometheus`) - Metrics collection. Not Angular-related.
5. **Heap Dump Endpoints** - Debug/monitoring. Not Angular-related.
6. **Morgan Logging** - Request logging. Not Angular-related.
7. **UA Parsing** - Browser detection for strict-dynamic CSP. Not Angular-related.

## Express 5 Route Patterns Used

SSR servers use Express 5 syntax. Key patterns:
- `/{*path}` for catch-all routes (NOT `/**` or `*` which are Express 4)
- Regex patterns like `/^\/some-section\/.*$/`
- Named params like `/:resource/:id/:slug`
- These should NOT change during Angular upgrades unless Express itself is upgraded

## Middleware Ordering Constraint

If the upgrade adds or moves any Express middleware in `src/server.ts`, the **Angular SSR handler must remain the last route handler before the error handler**. Anything registered after it will not run for SSR-rendered routes.

## Native Federation SSR

If the project is a **Native Federation** host/remote (see `references/native-federation.md`), federated SSR differs from the plain Express-server layout above:

- Federation is initialized **server-side** before Angular renders (import maps on the server).
- **Adapter v18–19**: the project has both `server.ts` and `bootstrap.server.ts`.
- **Adapter v20+**: the build generates `dist/{project}/server/fstart.mjs` ("federation start"), which initializes federation and then delegates to the CLI-generated `server.mjs`. On migrating to v20 you can delete `server.ts` and rename `bootstrap.server.ts` → `server.ts`.
- **Start the SSR server with `node fstart.mjs`, not `node server.mjs`** (v20+) — running `server.mjs` directly skips federation init and remotes won't resolve server-side. This also changes the PM2 entry point (see `references/pm2-and-deployment.md`).
- Keep the **Classic Runtime** on the SSR path — the v4 Orchestrator runtime is client-side only and will not execute remote modules during SSR.
- The custom `server.ts` concerns (CSP/nonce, redirects, Prometheus, Morgan) still apply, but live in the `server.mjs` that `fstart.mjs` delegates to — confirm the federation-start wrapper preserves them.

## Common SSR Upgrade Issues

1. **Build succeeds but server crashes at runtime**: Often caused by changes in `@angular/ssr/node` API. Test with `pnpm serve:ssr:dev` after build.
2. **Vite failing to bundle SSR**: Check `externalDependencies` in angular.json. Native modules like `canvas` must be external.
3. **TransferState issues**: If TranslateModule server/browser loader pattern breaks, check `@ngx-translate` compatibility.
4. **XHR factory errors**: The `ServerXhr` class wraps `xhr2` for server-side HTTP. Check if xhr2 is still compatible.
