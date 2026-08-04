#!/usr/bin/env bash
#
# federation-discovery.sh — Native Federation cross-repo discovery + singleton reconciliation helper.
#
# Given one or more GitLab groups (and optional explicit extra repos for a host that lives outside
# the group), this reads each project's package.json + federation.config.* via the GitLab raw-file
# API (NO cloning), classifies each as a Native Federation host/remote, parses the config to enumerate
# the actual shared singleton set (explicit `share({...})` keys or `shareAll` dependencies, minus
# `skip`), records each singleton's version per repo, and emits:
#   - <out>/federation-inventory.tsv   (one row per federated repo)
#   - <out>/federation-singletons.json (reconciliation manifest SKELETON: union of singletons with
#                                        every observed version + a drift flag; pin values are left
#                                        blank for the supervised step to fill)
# It is read-only and repo-agnostic — no hardcoded paths. It proposes; a human pins the final values.
#
# Usage:
#   GITLAB_HOST=gitlab.example.com \
#   TOKEN_FILE=~/.your-git-token \
#   GITLAB_GROUPS="your-group/frontend-remotes" \            # comma-sep group paths (NOT "GROUPS" — bash builtin)
#   EXTRA_REPOS="your-group/app-shell,your-group/frontend-remotes/catalog@feat/nf-migration" \  # hosts/repos outside groups; append @ref to pin a mid-migration branch
#   NG_TARGET=22 \                                     # optional: pre-fill suggested_pin per singleton
#   OUT=AI/federation \
#   ./federation-discovery.sh
#
# Host detection: to stay fast on large fleets, group members are treated as remotes; a host manifest
# is only probed for repos passed via EXTRA_REPOS (or when a root federation.config declares
# remotes/initFederation). Always pass the host repo(s) via EXTRA_REPOS so they're classified.
#
# Requires: bash, curl, jq. Token needs GitLab API read scope (read_api).

set -euo pipefail

GITLAB_HOST="${GITLAB_HOST:?set GITLAB_HOST (e.g. gitlab.example.com)}"
TOKEN_FILE="${TOKEN_FILE:-$HOME/.your-git-token}"
GITLAB_GROUPS="${GITLAB_GROUPS:-}"   # NB: not GROUPS — that name is a reserved bash builtin (gid array)
EXTRA_REPOS="${EXTRA_REPOS:-}"
OUT="${OUT:-AI/federation}"
NG_TARGET="${NG_TARGET:-}"   # optional target Angular major (e.g. 22) → pre-fills suggested_pin per singleton
API="https://${GITLAB_HOST}/api/v4"

command -v jq >/dev/null || { echo "jq is required — install: brew install jq (macOS) / apt-get install -y jq (Debian/CI)" >&2; exit 1; }
[ -r "$TOKEN_FILE" ] || { echo "token file not readable: $TOKEN_FILE" >&2; exit 1; }
TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
mkdir -p "$OUT"
INV="$OUT/federation-inventory.tsv"
: > "$INV"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
# Keep the PAT out of process argv (readable via ps / /proc on shared hosts): pass it as a 0600 header
# file that curl reads with `-H @file`, so only the file path — never the token — appears in argv.
HDRFILE="$tmp/.gl_hdr"; (umask 077; printf 'PRIVATE-TOKEN: %s\n' "$TOKEN" > "$HDRFILE")
HDR=(-H "@$HDRFILE")

enc () { jq -rn --arg s "$1" '$s|@uri'; }
raw () { curl -fsS --connect-timeout 5 --max-time 15 "${HDR[@]}" "$API/projects/$1/repository/files/$(enc "$2")/raw?ref=$(enc "$3")" 2>/dev/null; }
probe () { curl -o /dev/null -s --connect-timeout 4 --max-time 8 -w "%{http_code}" "${HDR[@]}" "$API/projects/$1/repository/files/$(enc "$2")/raw?ref=$(enc "$3")"; }

# Resolve inputs → list of "id<TAB>branch<TAB>shortname"
list_group () {
  local g page=1
  g="$(enc "$1")"
  while :; do
    local batch
    batch="$(curl -fsS --max-time 40 "${HDR[@]}" \
      "$API/groups/$g/projects?include_subgroups=true&per_page=100&page=$page&simple=true" 2>/dev/null || true)"
    [ -z "$batch" ] && break
    [ "$(echo "$batch" | jq 'length' 2>/dev/null || echo 0)" = "0" ] && break
    echo "$batch" | jq -r '.[] | "\(.id)\t\(.default_branch // "master")\t\(.path_with_namespace|split("/")|last)\tgroup"'
    page=$((page+1)); [ "$page" -gt 20 ] && break
  done
}
resolve_repo () {   # explicit "group/sub/project" or "group/sub/project@ref" → id row (ref for mid-migration branches)
  local spec="$1" path ref p
  path="${spec%@*}"; ref=""; case "$spec" in *@*) ref="${spec#*@}";; esac
  p="$(enc "$path")"
  curl -fsS --connect-timeout 5 --max-time 20 "${HDR[@]}" "$API/projects/$p" 2>/dev/null \
    | jq -r --arg ref "$ref" '"\(.id)\t\(if $ref!="" then $ref else (.default_branch // "master") end)\t\(.path_with_namespace|split("/")|last)\textra"'
}

{
  IFS=',' read -ra GS <<< "$GITLAB_GROUPS"; for g in "${GS[@]}";  do [ -n "$g" ] && list_group "$g"; done
  IFS=',' read -ra RS <<< "$EXTRA_REPOS"; for r in "${RS[@]}"; do [ -n "$r" ] && resolve_repo "$r"; done
} | sort -u > "$tmp/projects.tsv"

printf 'name\tfederated\tline\trole\tng_core\tcdk\tmaterial\trxjs\tzone\ttslib\tadapter\tshared\n' | tee "$INV"

: > "$tmp/sing.jsonl"   # ensure it exists even if no federated repo is found (else the manifest jq below fails under set -e)

while IFS=$'\t' read -r ID BR NAME SRC; do
  [ -z "${ID:-}" ] && continue
  pj="$(raw "$ID" "package.json" "$BR" || true)"
  [ -z "$pj" ] && continue
  adapter="$(echo "$pj" | jq -r '[.dependencies,.devDependencies]|add|to_entries[]?|select(.key|test("native-federation"))|"\(.key)@\(.value)"' 2>/dev/null | paste -sd, - || true)"
  if [ -z "$adapter" ]; then           # not Native Federation
    mf="$(echo "$pj" | jq -r '[.dependencies,.devDependencies]|add|to_entries[]?|select(.key|test("module-federation"))|.key' 2>/dev/null | paste -sd, - || true)"
    [ -n "$mf" ] && echo "note: $NAME uses Module Federation ($mf) — NOT supported by this skill, skipped" >&2
    continue
  fi

  # The config is NOT always at the repo root — verified in one fleet: 3 repos keep it at root while
  # 2 keep it at src/federation.config.mjs. Probing root only made those 2 silently fall back to the
  # framework shortlist, hiding their real shared set. Probe the known locations in order.
  cfg=""; cfgpath="-"
  for c in federation.config.mjs federation.config.js federation.config.ts \
           src/federation.config.mjs src/federation.config.js src/federation.config.ts; do
    if raw "$ID" "$c" "$BR" >"$tmp/c" 2>/dev/null && [ -s "$tmp/c" ]; then
      cfg="$(cat "$tmp/c")"; cfgpath="$c"; break
    fi
  done
  # Adapter package name is the ONLY reliable v3/v4 signal — a file extension is not (a v3 project can
  # ship an .mjs config). Derive the line from the installed adapter, never from the config filename.
  case "$adapter" in
    *native-federation-v4*) line="v4" ;;
    *native-federation*)    line="v3" ;;
    *)                      line="-"  ;;
  esac

  role=""; exposes=""; hostsig=""
  if [ -n "$cfg" ]; then
    echo "$cfg" | grep -q "exposes" && { role="remote"; exposes=1; }
    echo "$cfg" | grep -qE "remotes|loadManifest|initFederation" && hostsig=1
  fi
  # Manifest probe is the expensive part. Only run it for host candidates:
  #   - repos passed explicitly via EXTRA_REPOS (SRC=extra) — that's how hosts are supplied, or
  #   - a repo whose root config already hints at host intent.
  # Group members without host-hinting config are treated as remotes (no blind probing).
  if [ -z "$hostsig" ] && [ "$SRC" = "extra" ]; then
    for p in public/federation.manifest.json src/assets/federation.manifest.json src/assets/config/federation.manifest.json public/assets/federation.manifest.json; do
      [ "$(probe "$ID" "$p" "$BR")" = "200" ] && { hostsig=1; break; }
    done
  fi
  [ -n "$hostsig" ] && role="${role:+$role+}host"; role="${role:-remote}"

  get () { echo "$pj" | jq -r "[.dependencies,.devDependencies]|add|.[\"$1\"] // \"-\""; }

  # Derive the SHARED singleton set this repo actually federates, from federation.config:
  #   shareAll(...)                       → all runtime `dependencies`
  #   explicit share({ 'pkg': {...} })    → the quoted package keys (a common actual pattern)
  #   minus any `skip: [...]` list; the framework shortlist is always unioned in as a floor.
  SHORTLIST=$'@angular/core\n@angular/common\n@angular/router\n@angular/forms\n@angular/animations\n@angular/cdk\n@angular/material\nrxjs\nzone.js\ntslib'
  skiplist="$(printf '%s' "$cfg" | tr '\n' ' ' | grep -oE 'skip:[[:space:]]*\[[^]]*\]' | grep -oE "'[^']*'|\"[^\"]*\"" | tr -d "\"'" | paste -sd'|' - || true)"
  # explicit share({ '<pkg>': ... }) keys. The value may be an object literal (`: {`) OR a helper call
  # (`: singleton(...)`, `: shareUnpinned(...)`) — anchoring on `: {` alone silently drops every
  # helper-valued entry. Verified on a real config: `: {` found 1 key while this pattern found 4,
  # including a package that was actually drifting across the fleet. Path-like exposes keys are dropped.
  sharekeys="$(printf '%s' "$cfg" \
    | grep -oE "['\"][^'\"]+['\"][[:space:]]*:[[:space:]]*(\{|[A-Za-z_\$][A-Za-z0-9_\$]*\()" \
    | grep -oE "^['\"][^'\"]+['\"]" | tr -d "\"'" \
    | grep -vE '^[./]|[[:space:]]' | sort -u || true)"
  # A spread of an imported share map (`...platformShared` from a shared contract package) is INVISIBLE
  # to any static parse — the package names live in another package entirely. When present, the count
  # below is a FLOOR, not the set: it is marked with a trailing `!` so it can never masquerade as a
  # complete parse. Resolve the true set locally (see references/post-deploy-verification.md).
  spreads="$(printf '%s' "$cfg" | grep -oE '\.\.\.[A-Za-z_$][A-Za-z0-9_$]*\(?' \
    | grep -v '($' | sed 's/^\.\.\.//' | sort -u | paste -sd, - || true)"
  if printf '%s' "$cfg" | grep -q 'shareAll'; then
    depnames="$(echo "$pj" | jq -r '.dependencies // {} | keys[]' 2>/dev/null || true)"; shared_kind="shareAll"
  elif [ -n "$sharekeys" ]; then
    depnames=""; shared_kind="share"
  else
    depnames=""; shared_kind="${cfg:+cfg?}"; shared_kind="${shared_kind:-shortlist}"
  fi
  [ -n "$spreads" ] && { shared_kind="$shared_kind!"; printf 'note: %s share map spreads [%s] — static parse is a FLOOR only; resolve locally (config: %s)\n' "$NAME" "$spreads" "$cfgpath" >&2; }
  shared_names="$(printf '%s\n%s\n%s\n' "$depnames" "$sharekeys" "$SHORTLIST" | sort -u | grep -vE '^$' || true)"
  [ -n "$skiplist" ] && shared_names="$(printf '%s\n' "$shared_names" | grep -vE "^($skiplist)$" || true)"
  shared_json="$(printf '%s\n' "$shared_names" | jq -R -s -c 'split("\n")|map(select(.!=""))')"
  scount="$(printf '%s' "$shared_json" | jq 'length')"

  row=$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
    "$NAME" "yes" "$line" "$role" "$(get @angular/core)" "$(get @angular/cdk)" \
    "$(get @angular/material)" "$(get rxjs)" "$(get zone.js)" "$(get tslib)" "$adapter" "$shared_kind($scount)")
  printf '%s\n' "$row" | tee -a "$INV"

  # accumulate {pkg,version,repo} for every SHARED dep present in this repo (one jq call)
  echo "$pj" | jq -c --argjson names "$shared_json" --arg repo "$NAME" \
    '([.dependencies,.devDependencies]|add) as $d | $names[] | select($d[.] != null) | {pkg:., version:$d[.], repo:$repo}' \
    >> "$tmp/sing.jsonl" 2>/dev/null || true
done < "$tmp/projects.tsv"

# Build reconciliation manifest skeleton: per singleton, all observed versions + drift flag
jq -s '
  group_by(.pkg)[] | {
    (.[0].pkg): {
      observed: (map({(.repo): .version}) | add),
      distinct_versions: (map(.version) | unique),
      drift: ((map(.version) | unique | length) > 1),
      suggested_pin: "",   # pre-filled from npm when NG_TARGET is set (a suggestion — confirm it)
      pin: ""              # <-- the final value you commit; must be identical across all repos
    }
  }' "$tmp/sing.jsonl" 2>/dev/null | jq -s 'add // {}' > "$OUT/federation-singletons.json"

# Optional: resolve target-Angular-compatible suggested pins via npm (NG_TARGET=<major>).
if [ -n "$NG_TARGET" ]; then
  if ! command -v npm >/dev/null; then
    echo "NG_TARGET set but npm not found — leaving suggested_pin blank" >&2
  else
    # `npm view <pkg>@<major> …` matches a RANGE → returns a JSON array (one entry per version).
    # `last` collapses array→last element (newest patch) or passes a scalar through unchanged.
    last () { jq -r 'if type=="array" then .[-1] else . end' 2>/dev/null; }
    ver ()  { npm view "$1" version --json 2>/dev/null | last; }
    corev="$(ver "@angular/core@$NG_TARGET")"
    ngpeers="$(npm view "@angular/core@$NG_TARGET" peerDependencies --json 2>/dev/null | jq -c 'if type=="array" then .[-1] else . end' 2>/dev/null)"
    tslibv="$(npm view "@angular/core@$NG_TARGET" dependencies.tslib --json 2>/dev/null | last)"
    cp "$OUT/federation-singletons.json" "$tmp/m.json"
    for k in $(jq -r 'keys[]' "$tmp/m.json"); do
      case "$k" in
        @angular/*) sug="$(ver "$k@$NG_TARGET")"; [ -z "$sug" ] || [ "$sug" = "null" ] && sug="$corev" ;;
        rxjs|zone.js) sug="$(printf '%s' "$ngpeers" | jq -r --arg k "$k" '.[$k] // ""' 2>/dev/null)" ;;  # range Angular declares
        tslib) sug="$tslibv" ;;
        *) sug="" ;;   # design-system / state libs: resolve manually (peer-check the pkg)
      esac
      [ "$sug" = "null" ] && sug=""
      jq --arg k "$k" --arg s "$sug" '(.[$k].suggested_pin)=$s' "$tmp/m.json" > "$tmp/m2.json" && mv "$tmp/m2.json" "$tmp/m.json"
    done
    mv "$tmp/m.json" "$OUT/federation-singletons.json"
    echo "Resolved suggested_pin for Angular v$NG_TARGET (@angular/* → exact latest patch; rxjs/zone.js → Angular's declared peer range; tslib → Angular's dep range)."
  fi
fi

echo
echo "Wrote: $INV"
echo "Wrote: $OUT/federation-singletons.json  (fill in each \"pin\" during reconciliation)"
echo
echo "Singletons with version drift across repos (must be reconciled to ONE pin):"
jq -r 'to_entries[] | select(.value.drift) | "  \(.key): \(.value.distinct_versions|join("  vs  "))"' \
  "$OUT/federation-singletons.json" || true
