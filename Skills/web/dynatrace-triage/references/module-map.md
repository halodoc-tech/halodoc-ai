# Module Map

Use top pages and route fragments as source-location hints.

**Configure this for your project** — replace the example rows below with
your own route-to-module mapping. A useful module map is short and only
needs entries for routes that don't obviously map to their module by name.

Example shape (adapt to your own app's routing):

```text
- `/checkout/*`, `/cart/*`:
  likely `src/app/modules/checkout` or `src/app/modules/cart`
- `/search`, `/category/*`:
  likely `src/app/modules/catalog` or `src/app/modules/search`
- `/account/*`, `/profile/*`:
  likely `src/app/modules/account`
- homepage `/`:
  often core shell, shared modules, ads/widgets, or cross-feature components
```

Build yours by skimming your routing module(s) once and noting any route
prefix that isn't an obvious match for its feature module's folder name.

Use this as a routing hint, not proof. Always combine with at least one
other signal before claiming high source confidence.
