# Path Query Recipe

Each entry in `PATH_QUERIES` is one Angular dynamic route → one GSC API call. Get this entry right and the rest of the pipeline falls into place. Get it wrong and you'll prerender the wrong URLs, miss segments entirely, or blow your build budget.

---

## Anatomy of a `PATH_QUERIES` entry

```js
{
  name: 'articles',                                                   // 1
  regex: '^https://www\\.example\\.com/articles/[^/]+',              // 2
  paramKey: 'slug',                                                   // 3
  prefix: '/articles/',                                               // 4
  limit: MAX_PRERENDER.articles,                                      // 5
  filterRow: (pageUrl) => !String(pageUrl).includes('/category/'),   // 6 (optional)
}
```

| # | Field | Notes |
|---|---|---|
| 1 | `name` | Key under `gscPrerenderParamsData`. Use camelCase. Must match the key in `MAX_PRERENDER` and the property used in `app.routes.server.ts`. |
| 2 | `regex` | RE2 syntax — sent to GSC API. **No lookahead, no lookbehind, no backreferences.** Anchor with `^`. Do not anchor the end (`$`) unless you really mean only that exact path; leaving it open lets GSC return rows with query strings, which the script normalises. |
| 3 | `paramKey` | Must equal the `:param` name in the Angular route definition (e.g. route `articles/:slug` → `paramKey: 'slug'`). Mismatch = silent skip during prerender. |
| 4 | `prefix` | Pathname (not full URL) prefix used to slice the param out. Always start with `/` and end with `/`. |
| 5 | `limit` | Top N pages by clicks. Sourced from `MAX_PRERENDER` so the budget lives in one place. |
| 6 | `filterRow` | Optional JS predicate when `regex` can't exclude something. Receives the full page URL (the first GSC dimension key). Return `true` to keep. |

---

## Picking a regex

The regex runs server-side at GSC against the full page URL (including protocol and host). Practical rules:

- **Start with the host.** `^https://www\\.example\\.com/...` keeps you scoped to canonical URLs.
- **Match a single segment.** `[^/]+` after the prefix is right for one-level dynamic routes (`/articles/:slug`). It also matches segments that contain dots, hyphens, etc.
- **Don't end-anchor unless you mean it.** The script's `extractParam` already drops nested paths and trailing slashes. Leaving the regex open-ended catches rows where GSC kept query strings on the URL.
- **Escape literal dots.** `www\\.example\\.com`, not `www.example.com`. Within a JS string literal, that's two backslashes.

### When `regex` can't do the job alone

RE2 has no lookahead, so you can't say "match `/products/<slug>` **except** `/products/category/<slug>`" in the regex itself. Instead:

1. Write the broad regex (`^https://www\\.example\\.com/products/[^/]+`).
2. Add `filterRow: (pageUrl) => !String(pageUrl ?? '').includes('/category/')`.
3. Optionally add a separate `PATH_QUERIES` entry for the `/products/category/:slug` route with its own narrower regex.

This split is the standard pattern when two dynamic routes share a common prefix.

---

## Picking a click `limit`

Each prerendered page is one headless-browser render at build time. Cost grows linearly. Tune per path:

- Start at **10** for a new path. Watch the build duration delta after the first run.
- Bump to 25–50 once the path is proven and the build budget allows.
- Hot, short-lived content (news, seasonal articles) can justify a higher limit because the click distribution has a long tail.
- Stable evergreen content can go lower — the same top pages tend to appear consistently across weekly query windows, so a low limit still captures your most important routes.

The script de-duplicates within a path, so `limit` is the count of **unique** params after sort.

---

## Avoiding common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `regex` matches nested paths | Prerender includes pages like `/articles/foo/bar` | Keep `[^/]+` (already excludes `/`); don't widen to `.+`. |
| `prefix` doesn't end with `/` | `extractParam` returns the wrong slice | Always end the prefix with `/`. |
| `paramKey` mismatch | Build runs but the dynamic route isn't actually prerendered | Diff the `:param` in the Angular route against the `paramKey`. |
| Two paths overlap (e.g. `/foo/:slug` and `/foo/category/:slug`) | Category pages get added to the slug path | Use a `filterRow` on the broader path to exclude the narrower one, and add a dedicated entry for the narrower one. |
| `name` collision | Generated TS file overwrites entries | Each `PATH_QUERIES.name` must be unique. |
| End-anchoring with `$` | Empty results because GSC URLs have query strings | Drop the `$` unless you've confirmed every URL is bare. |

---

## Sanity-checking before merging

Before you commit a new `PATH_QUERIES` entry, run the script locally and look at the JSON dumped to stdout:

```bash
npm run gsc-prerender
```

For each new path, confirm:

- The list isn't empty.
- The values look like real slugs/IDs from your site, not URL fragments or hashed IDs.
- No value contains `/`, `?`, or `#` — those leak through when the regex or prefix is off.
- The count is `≤ limit`.

If any of those fail, tighten the regex or add a `filterRow` rather than post-processing in the script writer — keep the data flow simple.

- Confirm the GSC property has traffic on those URLs within the last 7 days. Open GSC → Performance → filter by URL to verify. Note that GSC has a 2–3 day processing lag, so very recent traffic may not appear yet.
