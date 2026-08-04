# Deployment Checklist (post-upgrade)

Generate `AI/deployment-checklist.md` from this template in Phase 9. The point is to surface anything the deploy environment needs that a green build/test run does **not** guarantee — Node.js version being the big one.

## 1. Node.js / runtime

- [ ] Angular v{TO} minimum Node.js: **v{min}** (from the Angular v{TO} requirements).
- [ ] Local Node used for the upgrade: v{local}.
- [ ] Server / CI images currently run Node v{current}.
- [ ] **If {current} < {min}**: SRE must bump the Node version in the server images **and** CI build images before this deploys. Flag as a blocker.
- [ ] `engines.node` in `package.json` updated to match (if the project pins it).

## 2. Build & artifacts

- [ ] Production build command and output path unchanged (or document the change).
- [ ] SSR output entry point valid: `dist/server/server.mjs` (SSR projects).
- [ ] Any new build-memory requirement (`--max-old-space-size`) reflected in CI.

## 3. PM2 / process manager (SSR)

- [ ] `ecosystem.*.config.js` (prod / stage / preprod) entry point still valid after build.
- [ ] No change to cluster mode / instance-count assumptions.

## 4. Environment & config

- [ ] No new required env vars introduced by upgraded packages.
- [ ] Private registry / auth still resolves for internal packages.

## 4b. Native Federation (federated apps only)

- [ ] SSR entry point is `fstart.mjs` (adapter v20+), and PM2 / start command points at it — not `server.mjs`.
- [ ] `federation.manifest.json` for **each** environment (stage / preprod / prod) has the correct remote URLs.
- [ ] Each remote's `remoteEntry.json` is published and served at its configured URL.
- [ ] **Lockstep**: host and all remotes are on the same Angular major (shared runtime singletons). A mismatch breaks at runtime, not at build. Blocker until confirmed.
- [ ] Shared `singleton: true` libs resolve to the **reconciled pinned version** (identical across host + remotes — see the cross-repo singleton manifest), not just "compatible" ranges. **Same-Angular-major is not sufficient** — verify *every* shared entry, including third-party ones: an observed fleet passed the Angular-major check while carrying `@ngx-translate/core` at 14 / 16.0.4 / 17.0.0 and its loader nine majors apart. Prove it with the live sweep in `references/post-deploy-verification.md` §2, not by inspection.
- [ ] `strictVersion: false` singletons explicitly reviewed — these fail **silently** (negotiated winner substituted for everyone, no throw, no warning), unlike `strictVersion: true` which announces itself.
- [ ] Host `remoteEntry.json`, `federation.manifest.*.json`, and `index.html` are served `no-cache`/`no-store` — a long `max-age` **or an absent header** poisons warm browsers after the next deploy (`references/post-deploy-verification.md` §3).
- [ ] Shell cache-busts its own federation fetches per load (`cacheTag`) — the only mechanism that reaches browsers already holding a stale copy; a server-side header fix cannot.
- [ ] Verified in a **warm** browser profile that visited the previous deploy, not incognito (incognito cannot reproduce the stale-map class).
- [ ] **Blue/green promotion**: staging↔primary CDN config diffed; the only differences are origins and genuinely new routes. Promotion copies the staging *configuration* over primary, so cache policies / response-header policies / TTLs / viewer-protocol policy must already match primary.
- [ ] CSP for **each** environment allows every remote origin (`script-src` + `connect-src`) and the nonce covers the import-map / `es-module-shims` script tags — otherwise remotes fail at runtime under CSP (no build error).

## 5. Sign-off

- [ ] Upgrade report reviewed (status = PASS).
- [ ] SSR server boot verified (if applicable).
- [ ] SRE informed of any image / runtime changes above.

> Fill the `{...}` placeholders from the pre-flight discovery and the Node.js compatibility check. Anything left unchecked is a deploy blocker until resolved.
