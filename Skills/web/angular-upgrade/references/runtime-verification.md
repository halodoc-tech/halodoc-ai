# Runtime Verification Checks

Runnable boot checks used by Phase 3B (CSR) and Phase 4 (SSR). A green build does **not** prove the app
renders — these serve the app and assert a real Angular render (HTTP 200 **and** an `ng-version` marker,
not a 200 error page). Both rely on `bash` (`trap`, `[[ ]]`).

## CSR runtime check (Phase 3B)

Serve the app and verify the main page actually renders. If it fails, investigate (and surface to the
user) before proceeding — the `trap` guarantees `ng serve` never leaks the port on early exit.

```bash
PORT=4300
# Fail fast if the port is already taken — otherwise ng serve binds nothing and the poll loop burns 5 min returning 000.
if lsof -i :"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "❌ Port $PORT is already in use — free it (or change PORT) before the runtime check."
else
npx ng serve --port "$PORT" > AI/ng-serve.log 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null' EXIT   # guarantees ng serve is killed on any exit path

# Poll for readiness — cold compile commonly exceeds 30s; wait up to ~5 min.
code=000
for i in $(seq 1 60); do
  code=$(curl -s -o AI/ng-serve-body.html -w "%{http_code}" "http://localhost:$PORT" || echo 000)
  [[ "$code" == "200" ]] && break
  sleep 5
done

# Assert HTTP 200 AND that the page is a real Angular render (not a 200 error page).
if [[ "$code" != "200" ]]; then
  echo "❌ Runtime check FAILED — HTTP $code (see AI/ng-serve.log)"
elif ! grep -q 'ng-version=' AI/ng-serve-body.html; then
  echo "❌ Returned 200 but no ng-version marker — likely an error page"
else
  echo "✅ Runtime check passed (HTTP 200, ng-version present)"
fi
fi
```

> **Native Federation:** `ng serve` wires remotes **client-side only**. For a **remote**, additionally
> assert its federation entry is served (`curl -fsS http://localhost:$PORT/remoteEntry.json` returns
> JSON). For a **host**, treat a shell-only HTTP 200 as necessary-but-not-sufficient — remote-load
> failures are lazy/client-side and won't surface here (they need the lockstep-upgraded remotes actually
> running). See `references/native-federation.md`.

## SSR boot check (Phase 4)

A passing production build does not prove SSR works — the server can still crash on boot or throw at
request time (`@angular/ssr/node` API drift, `XhrFactory`/`xhr2`, externalized native deps). After the
SSR build succeeds, start the SSR dev server and confirm it serves a rendered page. Record the result
(and the SSR dev-server start time — see Phase 9) in the upgrade report; if it fails, surface it before
proceeding.

> **Native Federation (adapter v20+):** the check prefers `fstart.mjs` (federation-start) if the build
> emitted it — starting `server.mjs` directly skips federation init and remotes won't resolve
> server-side. Discover the real output path from `angular.json`. See `references/native-federation.md`.

```bash
# Use the project's SSR dev script if present (serve:ssr:dev / dev:ssr); else serve the build output.
# Native Federation (adapter v20+): prefer fstart.mjs (federation-start) if the build emitted it — server.mjs alone skips federation init.
PORT=4400
if lsof -i :"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "Port $PORT is already in use — free it (or change PORT) before the SSR boot check."
else
ENTRY=$(ls dist/*/server/fstart.mjs dist/server/fstart.mjs 2>/dev/null | head -1); ENTRY=${ENTRY:-dist/server/server.mjs}
( npm run serve:ssr:dev --silent 2>&1 || node "$ENTRY" 2>&1 ) > AI/ssr-serve.log &
SSR_PID=$!
trap 'kill $SSR_PID 2>/dev/null' EXIT

code=000
for i in $(seq 1 60); do
  code=$(curl -s -o AI/ssr-body.html -w "%{http_code}" "http://localhost:$PORT" || echo 000)
  [[ "$code" == "200" ]] && break
  sleep 5
done

if [[ "$code" != "200" ]]; then
  echo "Runtime check FAILED — HTTP $code (see AI/ssr-serve.log)"
elif grep -qiE 'ERROR|ExceptionHandler|TypeError' AI/ssr-serve.log; then
  echo "SSR responded 200 but the server log shows runtime errors (see AI/ssr-serve.log)"
elif ! grep -q 'ng-version=' AI/ssr-body.html; then
  echo "SSR returned 200 but no ng-version marker — likely an error page"
else
  echo "SSR server boots and renders (HTTP 200, ng-version present, clean log)"
fi
fi
```
